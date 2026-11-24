import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, EntityMentionRecord
from app.ingestion.entity_resolution import (
    EntityResolver,
    IngestionEntityResolver,
    base_entity_name,
    names_differ_in_version_or_number,
)
from tests.fakes.in_memory_indexers import FakeEntityVectorIndex


@pytest.mark.asyncio
async def test_entity_resolution_30_pair_benchmark() -> None:
    """Benchmark entity resolution precision/recall with version-aware policy.

    Policy: names differing in numbers/versions are NOT merged as same entity;
    they should be linked with VERSION_OF in ingestion.
    """
    resolver = EntityResolver()

    # 15 positive pairs (same entity, no version/number conflict)
    positives = [
        ("Postgres", "Database", "PostgreSQL", "Database"),
        ("Redis", "Cache", "redis-server", "Cache"),
        ("K8s", "Infrastructure", "Kubernetes", "Infrastructure"),
        ("PaymentGateway", "Service", "Payment-Gateway", "Service"),
        ("PaymentGateway", "Service", "payment-gw", "Service"),
        ("Alice Chen", "Person", "Alice Chen", "Person"),
        ("Bob Kumar", "Person", "Bob Kumar", "Person"),
        ("Elena Rostova", "Person", "Elena Rostova", "Person"),
        ("Dave Miller", "Person", "Dave Miller", "Person"),
        ("Qdrant", "Database", "Qdrant Vector DB", "Database"),
        ("Neo4j", "Database", "Neo4j Graph Database", "Database"),
        ("Redis Sentinel", "Infrastructure", "Redis Sentinel Cluster", "Infrastructure"),
        ("SRE Team", "Organization", "SRE Team", "Team"),
        ("CoreBanking", "Service", "Core Banking", "Service"),
        ("Access Control", "Control", "access control", "Control"),
    ]

    # 15 negative pairs (different entities OR version variants that must not merge)
    negatives = [
        ("PostgreSQL", "Database", "PostgreSQL 16", "Database"),  # version variant -> VERSION_OF
        ("Postgres", "Database", "PostgreSQL 16", "Database"),  # version variant
        ("CoreBanking", "Service", "CoreBanking v2", "Service"),  # version variant
        ("ISO/IEC 27001:2013", "Standard", "ISO/IEC 27001:2022", "Standard"),  # version variant
        ("PostgreSQL", "Database", "Neo4j", "Database"),
        ("Redis", "Cache", "Qdrant", "Database"),
        ("Alice Chen", "Person", "Bob Kumar", "Person"),
        ("Elena Rostova", "Person", "Dave Miller", "Person"),
        ("PaymentGateway", "Service", "CoreBanking", "Service"),
        ("Kubernetes", "Infrastructure", "PostgreSQL", "Database"),
        ("SRE Team", "Organization", "Data Platform Team", "Organization"),
        ("Payments Team", "Organization", "Core Banking Team", "Organization"),
        ("Exchange Rate Service", "Service", "PaymentGateway", "Service"),
        ("Board Audit", "Document", "SLA Agreement", "Document"),
        ("Docker", "Infrastructure", "PostgreSQL", "Database"),
    ]

    tp = fp = tn = fn = 0
    for a, ta, b, tb in positives:
        if await resolver.are_same_entity(a, ta, b, tb):
            tp += 1
        else:
            fn += 1
    for a, ta, b, tb in negatives:
        if not await resolver.are_same_entity(a, ta, b, tb):
            tn += 1
        else:
            fp += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    assert precision >= 0.90, f"Precision was {precision:.2%}"
    assert recall >= 0.90, f"Recall was {recall:.2%}"


def test_version_variants_not_merged_but_base_detected() -> None:
    assert names_differ_in_version_or_number("ISO/IEC 27001:2013", "ISO/IEC 27001:2022")
    assert names_differ_in_version_or_number("PostgreSQL", "PostgreSQL 16")
    base = base_entity_name("ISO/IEC 27001:2022")
    assert "27001" in base
    assert "2022" not in base


@pytest.mark.asyncio
async def test_shared_tools_across_docs_resolve_to_single_nodes_linked_to_both_docs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    idx = FakeEntityVectorIndex()
    async with factory() as session:
        resolver = IngestionEntityResolver(entity_index=idx, threshold=0.85, session=session)

        concept_tools = ["Python", "Electron", "PyMuPDF"]
        brd_tools = ["Python", "Electron", "PyMuPDF", "Docling"]

        resolved_concept = []
        for name in concept_tools:
            r, _ = await resolver.resolve(
                name=name,
                entity_type="Software",
                owner_user_id="usr_alice_01",
                doc_id="doc_concept",
                source_id="doc_concept",
            )
            resolved_concept.append(r)

        resolved_brd = []
        for name in brd_tools:
            r, _ = await resolver.resolve(
                name=name,
                entity_type="Software",
                owner_user_id="usr_alice_01",
                doc_id="doc_5brd",
                source_id="doc_5brd",
            )
            resolved_brd.append(r)

        await resolver.persist_mentions()
        await session.commit()

        by_name = {r.name.lower(): r for r in resolved_concept}
        by_name_brd = {r.name.lower(): r for r in resolved_brd}

        for tool in ["python", "electron", "pymupdf"]:
            assert by_name[tool].entity_id == by_name_brd[tool].entity_id
            q = await session.execute(
                select(EntityMentionRecord).where(
                    EntityMentionRecord.entity_id == by_name[tool].entity_id
                )
            )
            mentions = q.scalars().all()
            source_ids = {m.source_id for m in mentions}
            assert "doc_concept" in source_ids
            assert "doc_5brd" in source_ids
    await engine.dispose()

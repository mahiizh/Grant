from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.acl import ACLScope
from app.db.models import Base
from app.db.postgres import DocumentRepository
from app.ingestion import (
    EntityRelationExtractor,
    IngestionPipeline,
    chunk_parsed_document,
    parse_markdown,
)


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, in-memory SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


def test_parse_markdown_metadata_and_sections() -> None:
    sample_md = """# RFC 001: Hybrid Storage Architecture

**Document ID**: `doc_rfc_storage_001`
**Author**: Data Platform Team
**Status**: Accepted
**Last Updated**: 2026-03-15

## 1. Overview
The platform utilizes PostgreSQL 16, Qdrant, Neo4j, and Redis.

## 2. Ingestion Outbox
Writes go to PostgreSQL outbox table first.
"""
    parsed = parse_markdown(sample_md, source_path="corpus/rfc_001.md")
    assert parsed.title == "RFC 001: Hybrid Storage Architecture"
    assert parsed.doc_id == "doc_rfc_storage_001"
    assert parsed.metadata["status"] == "Accepted"
    assert len(parsed.sections) == 3  # Header metadata + Overview + Ingestion Outbox
    assert parsed.sections[1].heading == "1. Overview"
    assert "PostgreSQL 16" in parsed.sections[1].content


def test_chunking_parsed_document() -> None:
    sample_md = """# Test Title
**Document ID**: `doc_test_001`

## Section A
This is section A with some content text.

## Section B
This is section B with another set of words.
"""
    parsed = parse_markdown(sample_md)
    acl = ACLScope.public()
    chunks = chunk_parsed_document(parsed, source_uri="docs/test.md", acl_scope=acl)

    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk.doc_id == "doc_test_001"
        assert chunk.tokens is not None and chunk.tokens > 0
        assert chunk.chunk_id.startswith("chk_doc_test_001_")


def test_entity_relation_extraction() -> None:
    sample_text = (
        "PostgreSQL 16 is owned by the Data Platform Team. "
        "Alice Chen is the Team Lead for the Data Platform Team."
    )
    parsed = parse_markdown(f"# Test\n## Section 1\n{sample_text}")
    chunks = chunk_parsed_document(parsed, source_uri="docs/test.md")
    chunk = chunks[1]

    result = EntityRelationExtractor.extract_from_chunk(chunk)
    ent_names = {e.name for e in result.entities}
    assert "PostgreSQL 16" in ent_names
    assert "Data Platform Team" in ent_names

    ents, rels = EntityRelationExtractor.to_domain_graph(result, chunk)
    assert len(ents) >= 2
    predicates = {r.relation_type for r in rels}
    assert "OWNED_BY" in predicates or "LED_BY" in predicates


@pytest.mark.anyio
async def test_end_to_end_corpus_ingestion(
    test_session: AsyncSession,
    tmp_corpus_dir: Path,
) -> None:
    files = [
        tmp_corpus_dir / "rfc_001_storage_architecture.md",
        tmp_corpus_dir / "postmortem_inc_2026_04.md",
        tmp_corpus_dir / "team_directory_2026.md",
    ]

    for file_path in files:
        assert file_path.exists(), f"Corpus file missing: {file_path}"
        summary = await IngestionPipeline.ingest_file(
            session=test_session,
            file_path=file_path,
        )
        await test_session.flush()

        assert summary.chunk_count > 0
        assert summary.doc_id.startswith("doc_")

        # Verify document is stored in database and retrievable
        stored_doc = await DocumentRepository.get_document(
            session=test_session, doc_id=summary.doc_id
        )
        assert stored_doc is not None
        assert stored_doc.title == summary.title
        assert len(stored_doc.chunks) == summary.chunk_count


def test_pdf_upload_rejected_with_415() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/documents",
        files={"file": ("unsupported_spec.pdf", b"%PDF-1.4 dummy", "application/pdf")},
    )
    assert response.status_code == 415
    assert "PDF upload is not supported" in response.json()["detail"]

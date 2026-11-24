import hashlib
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import ACLScope
from app.core.config import get_settings
from app.db.postgres import DocumentRepository
from app.domain import Document, Entity, Provenance, Relation, TemporalBounds
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.conflicts import close_superseded_document_versions
from app.ingestion.extraction import EntityRelationExtractor
from app.ingestion.gliner_extraction import get_gliner_extractor
from app.ingestion.parse import parse_markdown

logger = logging.getLogger(__name__)

# Cache for chunk extraction results keyed by chunk text SHA-256 hash
_CHUNK_EXTRACTION_CACHE: dict[str, dict[str, Any]] = {}


class IngestionSummary(BaseModel):
    """Result summary of an ingested document."""

    doc_id: str
    title: str
    chunk_count: int
    entity_count: int
    relation_count: int
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tokens: int = 0
    cost_usd: float = 0.0


class IngestionPipeline:
    """End-to-end document parsing, chunking, graph extraction, and transactional persistence."""

    @classmethod
    async def ingest_text(
        cls,
        session: AsyncSession,
        content: str,
        source_uri: str,
        acl_scope: ACLScope | None = None,
        owner_user_id: str | None = None,
        entity_resolver: Any | None = None,
    ) -> IngestionSummary:
        """Ingest raw markdown text content into PostgreSQL and stage outbox index events."""
        parsed = parse_markdown(content, source_path=source_uri)

        # Respect scope from frontmatter if present and not explicitly overridden
        fm_scope = parsed.metadata.get("acl_scope")
        if acl_scope is not None:
            scope = acl_scope
        elif fm_scope:
            if fm_scope.lower() == "public":
                scope = ACLScope.public()
            else:
                scope = ACLScope.restricted(
                    allowed_roles=frozenset([fm_scope]),
                    allowed_groups=frozenset([fm_scope]),
                )
        else:
            scope = ACLScope.public()

        # Generate structure-aware chunks
        chunks = chunk_parsed_document(
            parsed=parsed,
            source_uri=source_uri,
            acl_scope=scope,
        )
        if owner_user_id is not None:
            chunks = [chunk.model_copy(update={"owner_user_id": owner_user_id}) for chunk in chunks]

        # Skip expensive extraction if content/index fingerprint is unchanged.
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            from app.db.models import DocumentRecord as DBDocumentRecord

            existing_stmt = (
                select(DBDocumentRecord)
                .options(selectinload(DBDocumentRecord.chunks))
                .where(DBDocumentRecord.doc_id == parsed.doc_id)
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                existing_fp = (
                    existing.content_hash or hashlib.sha256(existing.content.encode("utf-8")).hexdigest(),
                    existing.owner_user_id,
                    existing.acl_tenant_id,
                    tuple(sorted(existing.acl_allowed_roles or [])),
                    tuple(sorted(existing.acl_allowed_groups or [])),
                    existing.acl_is_public,
                    existing.valid_from.isoformat() if existing.valid_from else None,
                    existing.valid_to.isoformat() if existing.valid_to else None,
                )
                new_fp = (
                    content_hash,
                    owner_user_id,
                    scope.tenant_id,
                    tuple(sorted(scope.allowed_roles)),
                    tuple(sorted(scope.allowed_groups)),
                    scope.is_public,
                    (parsed.valid_from.isoformat() if parsed.valid_from else None),
                    (parsed.valid_to.isoformat() if parsed.valid_to else None),
                )
                if existing_fp == new_fp:
                    meta = existing.metadata_json or {}
                    return IngestionSummary(
                        doc_id=existing.doc_id,
                        title=existing.title,
                        chunk_count=len(existing.chunks),
                        entity_count=int(meta.get("entity_count", 0) or 0),
                        relation_count=int(meta.get("relation_count", 0) or 0),
                        entities=[],
                        relations=[],
                        tokens=int(meta.get("tokens", 0) or 0),
                        cost_usd=float(meta.get("cost_usd", 0.0) or 0.0),
                    )
        except Exception:
            logger.debug("Ingestion unchanged-check failed; proceeding with extraction", exc_info=True)

        all_entities: dict[str, Entity] = {}
        all_relations: list[Relation] = []
        total_tokens = 0
        total_cost = 0.0

        resolver = entity_resolver
        if resolver is None:
            try:
                from app.ingestion.entity_resolution import IngestionEntityResolver

                resolver = IngestionEntityResolver(session=session)
            except Exception:
                logger.exception("Failed to initialize IngestionEntityResolver; continuing without Qdrant resolution")
                resolver = None

        gliner_extractor = None
        gliner_used = False
        fallback_used = False
        try:
            gliner_extractor = get_gliner_extractor()
        except Exception:
            logger.exception("Failed to initialize GLiNER extractor; heuristic fallback will be used")

        for chunk in chunks:
            chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            if chunk_hash in _CHUNK_EXTRACTION_CACHE:
                cached_data = _CHUNK_EXTRACTION_CACHE[chunk_hash]
                ext_result = cached_data["result"]
                logger.debug("Reusing cached extraction for chunk %s ($0)", chunk.chunk_id)
            else:
                try:
                    if gliner_extractor is None:
                        raise RuntimeError("GLiNER extractor unavailable")
                    ext_result = gliner_extractor.extract_from_chunk(chunk)
                    gliner_used = True
                except Exception:
                    logger.exception("GLiNER extraction failed for chunk %s; using heuristic fallback", chunk.chunk_id)
                    ext_result = EntityRelationExtractor.extract_from_chunk(chunk)
                    fallback_used = True
                # Local extraction cost model: no LLM tokens/cost
                ext_tokens = 0
                ext_cost = 0.0
                _CHUNK_EXTRACTION_CACHE[chunk_hash] = {
                    "result": ext_result,
                    "tokens": ext_tokens,
                    "cost": ext_cost,
                }

            ents, rels = EntityRelationExtractor.to_domain_graph(ext_result, chunk)

            # Resolve entities against owner-scoped Qdrant entity vectors (SBERT).
            name_to_canonical: dict[str, str] = {}
            original_id_to_canonical: dict[str, str] = {}
            resolved_entities: list[Entity] = []
            extra_version_rels: list[Relation] = []
            if resolver is not None:
                for ent in ents:
                    try:
                        resolved, version_rels = await resolver.resolve(
                            name=ent.name,
                            entity_type=ent.entity_type,
                            owner_user_id=owner_user_id,
                            doc_id=parsed.doc_id,
                            source_id=parsed.doc_id,
                        )
                        canonical_ent = ent.model_copy(
                            update={
                                "entity_id": resolved.entity_id,
                                "name": resolved.name,
                                "entity_type": resolved.entity_type,
                                "canonical_id": resolved.canonical_id,
                                "properties": {
                                    **ent.properties,
                                    "aliases": resolved.aliases,
                                    "type_group": resolved.type_group,
                                    "owner_user_id": owner_user_id or "",
                                },
                            }
                        )
                        original_id_to_canonical[ent.entity_id] = resolved.entity_id
                        name_to_canonical[ent.name.strip().lower()] = resolved.entity_id
                        name_to_canonical[resolved.name.strip().lower()] = resolved.entity_id
                        resolved_entities.append(canonical_ent)
                        for vr in version_rels:
                            from app.domain.ids import generate_relation_id as _gen_rel_id

                            src_id = vr["source_entity_id"]
                            tgt_id = vr["target_entity_id"]
                            if not any(e.entity_id == tgt_id for e in resolved_entities):
                                resolved_entities.append(
                                    Entity(
                                        entity_id=tgt_id,
                                        name=str(vr.get("target_name") or tgt_id),
                                        entity_type=str(vr.get("target_entity_type") or resolved.entity_type),
                                        canonical_id=tgt_id,
                                        properties={
                                            "aliases": list(vr.get("target_aliases", []) or []),
                                            "type_group": str(vr.get("target_type_group") or ""),
                                            "owner_user_id": owner_user_id or "",
                                        },
                                        acl_scope=chunk.acl_scope,
                                        temporal=chunk.temporal,
                                        provenance=chunk.provenance,
                                    )
                                )
                            extra_version_rels.append(
                                Relation(
                                    relation_id=_gen_rel_id(src_id, "VERSION_OF", tgt_id),
                                    source_entity_id=src_id,
                                    target_entity_id=tgt_id,
                                    relation_type="VERSION_OF",
                                    description="Version variant linked to base entity",
                                    weight=1.0,
                                    source_chunk_ids=[chunk.chunk_id],
                                    acl_scope=chunk.acl_scope,
                                    temporal=chunk.temporal,
                                    provenance=chunk.provenance,
                                )
                            )
                    except Exception:
                        logger.exception("Entity resolution failed for %s; keeping original entity", ent.name)
                        resolved_entities.append(ent)
                ents = resolved_entities

            # Remap relation endpoints to canonical IDs.
            remapped_rels: list[Relation] = []
            for rel in rels:
                src_id = original_id_to_canonical.get(rel.source_entity_id, rel.source_entity_id)
                tgt_id = original_id_to_canonical.get(rel.target_entity_id, rel.target_entity_id)
                if src_id != rel.source_entity_id or tgt_id != rel.target_entity_id:
                    from app.domain.ids import generate_relation_id

                    remapped_rels.append(
                        rel.model_copy(
                            update={
                                "relation_id": generate_relation_id(src_id, rel.relation_type, tgt_id),
                                "source_entity_id": src_id,
                                "target_entity_id": tgt_id,
                            }
                        )
                    )
                else:
                    remapped_rels.append(rel)
            rels = remapped_rels + extra_version_rels

            # Store extracted entities/relations on chunk metadata so outbox can pass them
            chunk.metadata["entities"] = [
                {
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "aliases": list(e.properties.get("aliases", []) or []),
                }
                for e in ents
            ]
            chunk.metadata["relations"] = [
                {
                    "source_entity_id": r.source_entity_id,
                    "target_entity_id": r.target_entity_id,
                    "relation_type": r.relation_type,
                }
                for r in rels
            ]

            for ent in ents:
                if ent.entity_id not in all_entities:
                    all_entities[ent.entity_id] = ent
                else:
                    existing = all_entities[ent.entity_id]
                    existing.source_chunk_ids.append(chunk.chunk_id)
            all_relations.extend(rels)

        temporal = TemporalBounds(
            valid_from=parsed.valid_from,
            valid_to=parsed.valid_to,
        )
        source_tier = int(parsed.metadata.get("source_tier", 1))
        prov = Provenance.from_document(
            source_uri=source_uri,
            source_version=1,
            tier=source_tier,
        )

        doc_meta = dict(parsed.metadata)
        doc_meta["tokens"] = total_tokens
        doc_meta["cost_usd"] = round(total_cost, 6)
        doc_meta["entity_count"] = len(all_entities)
        doc_meta["relation_count"] = len(all_relations)
        doc_meta["extraction_engine"] = "gliner" if gliner_used and not fallback_used else ("mixed" if gliner_used and fallback_used else "heuristic")
        doc_meta["extraction_model"] = get_settings().GLINER_MODEL if gliner_used else ""
        doc_meta["extraction_status"] = "completed"

        doc = Document(
            doc_id=parsed.doc_id,
            title=parsed.title,
            content=content,
            chunks=chunks,
            owner_user_id=owner_user_id,
            acl_scope=scope,
            temporal=temporal,
            provenance=prov,
            version=1,
            metadata=doc_meta,
        )

        # Persist to PostgreSQL within the caller's transaction.
        # Order: save document -> delete that doc's old mentions -> insert new mentions.
        await DocumentRepository.save_document(session=session, document=doc)

        from sqlalchemy import delete as sa_delete

        from app.db.models import EntityMentionRecord

        await session.execute(
            sa_delete(EntityMentionRecord).where(
                EntityMentionRecord.source_id == doc.doc_id,
                EntityMentionRecord.source_kind == "document",
            )
        )

        if resolver is not None and hasattr(resolver, "persist_mentions"):
            await resolver.persist_mentions(session)

        # Invalidate / close validity on superseded prior versions (e.g. v1 when v2 arrives)
        await close_superseded_document_versions(session=session, new_doc=doc)

        return IngestionSummary(
            doc_id=doc.doc_id,
            title=doc.title,
            chunk_count=len(chunks),
            entity_count=len(all_entities),
            relation_count=len(all_relations),
            entities=list(all_entities.values()),
            relations=all_relations,
            tokens=total_tokens,
            cost_usd=round(total_cost, 6),
        )

    @classmethod
    async def ingest_file(
        cls,
        session: AsyncSession,
        file_path: str | Path,
        acl_scope: ACLScope | None = None,
        owner_user_id: str | None = None,
    ) -> IngestionSummary:
        """Read a file from disk and ingest it through the pipeline."""
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Source file not found at: {file_path}")

        content = path_obj.read_text(encoding="utf-8")
        return await cls.ingest_text(
            session=session,
            content=content,
            source_uri=str(path_obj.as_posix()),
            acl_scope=acl_scope,
            owner_user_id=owner_user_id,
        )

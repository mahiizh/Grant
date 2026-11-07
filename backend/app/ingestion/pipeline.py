import hashlib
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import ACLScope
from app.db.postgres import DocumentRepository
from app.domain import Document, Entity, Provenance, Relation, TemporalBounds
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.extraction import EntityRelationExtractor
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

        all_entities: dict[str, Entity] = {}
        all_relations: list[Relation] = []
        total_tokens = 0
        total_cost = 0.0

        for chunk in chunks:
            chunk_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            if chunk_hash in _CHUNK_EXTRACTION_CACHE:
                cached_data = _CHUNK_EXTRACTION_CACHE[chunk_hash]
                ext_result = cached_data["result"]
                # 0 tokens and $0 cost for unchanged/cached chunks!
                logger.debug("Reusing cached extraction for chunk %s ($0)", chunk.chunk_id)
            else:
                ext_result = EntityRelationExtractor.extract_from_chunk(chunk)
                # Compute token usage for extraction
                chunk_tokens = chunk.tokens or len(chunk.text.split())
                ext_tokens = chunk_tokens + 50
                ext_cost = round((ext_tokens * 0.000000075), 6)
                total_tokens += ext_tokens
                total_cost += ext_cost

                _CHUNK_EXTRACTION_CACHE[chunk_hash] = {
                    "result": ext_result,
                    "tokens": ext_tokens,
                    "cost": ext_cost,
                }

            ents, rels = EntityRelationExtractor.to_domain_graph(ext_result, chunk)

            # Store extracted entities/relations on chunk metadata so outbox can pass them
            chunk.metadata["entities"] = [
                {"entity_id": e.entity_id, "name": e.name, "entity_type": e.entity_type}
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
                    all_entities[ent.entity_id].source_chunk_ids.append(chunk.chunk_id)
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

        doc = Document(
            doc_id=parsed.doc_id,
            title=parsed.title,
            content=content,
            chunks=chunks,
            acl_scope=scope,
            temporal=temporal,
            provenance=prov,
            version=1,
            metadata=doc_meta,
        )

        # Persist to PostgreSQL within the caller's transaction
        await DocumentRepository.save_document(session=session, document=doc)

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
        )

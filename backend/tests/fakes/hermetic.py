from collections.abc import Sequence
from pathlib import Path

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Relation
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.corpus import iter_corpus_files
from app.ingestion.extraction import EntityRelationExtractor
from app.ingestion.parse import parse_markdown
from app.orchestration.workflow import RAGOrchestrator
from tests.fakes.fake_gateway import FakeModelGateway
from tests.fakes.in_memory_cache import FakeExactCache
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever,
    FakeDenseRetriever,
    FakeGraphRetriever,
    FakeHybridRetriever,
)


def _scope_for(metadata: dict[str, object]) -> ACLScope:
    """Mirror ingestion frontmatter parsing: only owner/shared are meaningful."""
    shared = metadata.get("shared_scope") or metadata.get("acl_scope")
    if shared and str(shared).lower() != "public":
        return ACLScope.shared(str(shared))
    return ACLScope.public()


def load_corpus_chunks(corpus_dir: Path | str) -> list[Chunk]:
    """Chunk a caller-supplied corpus directory without touching any demo corpus."""
    root = Path(corpus_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Corpus directory not found at: {root}")

    chunks: list[Chunk] = []
    for path in iter_corpus_files(root):
        parsed = parse_markdown(path.read_text(encoding="utf-8"), source_path=path.as_posix())
        scope = _scope_for(parsed.metadata)
        owner = parsed.metadata.get("owner_user_id")
        owner_user_id = str(owner) if owner else None
        produced = chunk_parsed_document(parsed, path.as_posix(), scope)
        if owner_user_id is not None:
            produced = [c.model_copy(update={"owner_user_id": owner_user_id}) for c in produced]
        chunks.extend(produced)
    return chunks


def build_hermetic_orchestrator(
    chunks: Sequence[Chunk],
) -> tuple[RAGOrchestrator, list[Chunk]]:
    """Build an in-memory orchestrator over the supplied chunks.

    No Redis, Qdrant, Neo4j, PostgreSQL, network, or API key is touched.
    """
    materialized = list(chunks)
    all_entities: dict[str, Entity] = {}
    all_relations: list[Relation] = []

    for chunk in materialized:
        result = EntityRelationExtractor.extract_from_chunk(chunk)
        entities, relations = EntityRelationExtractor.to_domain_graph(result, chunk)
        for entity in entities:
            if entity.entity_id not in all_entities:
                all_entities[entity.entity_id] = entity
            else:
                existing = all_entities[entity.entity_id]
                all_entities[entity.entity_id] = existing.model_copy(
                    update={
                        "acl_scope": existing.acl_scope.union(entity.acl_scope),
                        "source_chunk_ids": list(
                            dict.fromkeys(existing.source_chunk_ids + entity.source_chunk_ids)
                        ),
                    }
                )
        all_relations.extend(relations)

    dense = FakeDenseRetriever(embedding_dim=128)
    sparse = FakeBM25Retriever()
    hybrid = FakeHybridRetriever(dense=dense, sparse=sparse)
    hybrid.index_chunks(materialized)

    graph = FakeGraphRetriever()
    graph.index_graph(list(all_entities.values()), all_relations, materialized)

    orchestrator = RAGOrchestrator(
        hybrid_retriever=hybrid,  # type: ignore[arg-type]
        graph_retriever=graph,  # type: ignore[arg-type]
        exact_cache=FakeExactCache(),  # type: ignore[arg-type]
        model_gateway=FakeModelGateway(),
    )
    return orchestrator, materialized

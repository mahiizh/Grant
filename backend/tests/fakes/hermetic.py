from collections.abc import Sequence
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Relation
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.extraction import EntityRelationExtractor
from app.ingestion.parse import parse_markdown
from app.orchestration.workflow import RAGOrchestrator
from tests.fakes.fake_gateway import FakeModelGateway
from tests.fakes.in_memory_cache import FakeExactCache, FakeSemanticCache
from tests.fakes.in_memory_retrievers import (
    FakeBM25Retriever,
    FakeDenseRetriever,
    FakeGraphRetriever,
    FakeHybridRetriever,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scope_for(parsed_scope: str | None) -> ACLScope:
    if parsed_scope and parsed_scope.lower() != "public":
        return ACLScope.restricted(
            allowed_roles=frozenset([parsed_scope]),
            allowed_groups=frozenset([parsed_scope]),
        )
    return ACLScope.public()


def load_corpus_chunks(corpus_dir: Path | str | None = None) -> list[Chunk]:
    """Reproduce the ingestion chunker over the corpus without any external store.

    Includes the adversarial documents, mirroring ``app.ingestion.cli``, so the
    hermetic harness sees exactly the 15 documents / 45 chunks a live ingest does.
    """
    root = Path(corpus_dir) if corpus_dir is not None else REPO_ROOT / "corpus"
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory not found at: {root}")

    files = sorted(root.glob("*.md"))
    adversarial = root / "adversarial"
    if adversarial.exists():
        files.extend(sorted(adversarial.glob("*.md")))

    chunks: list[Chunk] = []
    for path in files:
        if path.name.lower() == "readme.md":
            continue
        parsed = parse_markdown(path.read_text(encoding="utf-8"), source_path=path.as_posix())
        scope = _scope_for(parsed.metadata.get("acl_scope"))
        chunks.extend(chunk_parsed_document(parsed, path.as_posix(), scope))
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
                all_entities[entity.entity_id].source_chunk_ids.append(chunk.chunk_id)
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
        semantic_cache=FakeSemanticCache(similarity_threshold=0.45),  # type: ignore[arg-type]
        model_gateway=FakeModelGateway(),
        checkpointer=MemorySaver(),
    )
    return orchestrator, materialized

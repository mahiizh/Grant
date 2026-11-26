import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores
from app.domain import Evidence, Provenance, SourceTier
from app.observability.stage_timing import timed_async_stage
from app.retrieval.filters import RetrievalFilter

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Production Graph retriever executing Cypher multi-hop traversals over Neo4j."""

    def __init__(
        self,
        driver: AsyncDriver | None = None,
        entity_index: Any | None = None,
    ) -> None:
        settings = get_settings()
        assert_writable_stores(settings)
        self.driver = driver or AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self._entity_index = entity_index

    @staticmethod
    def _criteria(filter_criteria: RetrievalFilter | None) -> RetrievalFilter:
        """Default to a public-only filter when no caller identity is supplied."""
        return filter_criteria or RetrievalFilter()

    @timed_async_stage("neo4j")
    async def find_path(
        self,
        start_entity_name: str,
        target_entity_name: str,
        max_depth: int = 4,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[str] | None:
        """Find the shortest ACL-permitted path between two entities in Neo4j.

        ``shortestPath(... ) WHERE ALL(...)`` would only reject the single shortest
        path, not search for the shortest *allowed* one. The graph is small, so we
        enumerate bounded paths, filter them, and take the shortest survivor.
        """
        criteria = self._criteria(filter_criteria)
        node_pred, params = criteria.to_cypher_predicate("n")
        rel_pred, _ = criteria.to_cypher_predicate("r")
        start_pred, _ = criteria.to_cypher_predicate("a")
        target_pred, _ = criteria.to_cypher_predicate("b")

        cypher = f"""
        MATCH (a:Entity), (b:Entity)
        WHERE toLower(a.name) = toLower($start)
          AND toLower(b.name) = toLower($target)
          AND {start_pred}
          AND {target_pred}
        MATCH path = (a)-[*..{max_depth}]-(b)
        WHERE ALL(n IN nodes(path) WHERE 'Entity' IN labels(n) AND {node_pred})
          AND ALL(r IN relationships(path) WHERE {rel_pred})
        RETURN [n IN nodes(path) | n.name] AS node_names,
               [r IN relationships(path) | type(r)] AS rel_types
        ORDER BY length(path)
        LIMIT 1
        """
        async with self.driver.session(database=get_settings().NEO4J_DATABASE) as session:
            res = await session.run(
                cypher,
                start=start_entity_name.strip(),
                target=target_entity_name.strip(),
                **params,
            )
            record = await res.single()
            if not record:
                return None

            node_names = record["node_names"]
            rel_types = record["rel_types"]

            # Interleave node names and relationship predicates: [A, REL, B, REL, C]
            path_tokens: list[str] = []
            for i, name in enumerate(node_names):
                path_tokens.append(name)
                if i < len(rel_types):
                    path_tokens.append(rel_types[i])

            return path_tokens

    @timed_async_stage("neo4j")
    async def retrieve_path_evidence(
        self,
        path_tokens: list[str],
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[Evidence]:
        """Fetch ACL-permitted source chunks linked to the entities in a reasoning path."""
        # Extract entity names (even positions)
        entity_names = [token for i, token in enumerate(path_tokens) if i % 2 == 0]
        if not entity_names:
            return []

        criteria = self._criteria(filter_criteria)
        chunk_pred, params = criteria.to_cypher_predicate("c")

        cypher = f"""
        MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
        WHERE e.name IN $entity_names
          AND {chunk_pred}
        RETURN DISTINCT c.chunk_id AS chunk_id,
                        c.doc_id AS doc_id,
                        c.text AS text
        LIMIT $limit
        """
        evidence_list: list[Evidence] = []
        async with self.driver.session(database=get_settings().NEO4J_DATABASE) as session:
            res = await session.run(
                cypher,
                entity_names=entity_names,
                limit=top_k * 2,
                **params,
            )
            records = await res.data()

            # Group candidates by doc_id to ensure multi-doc diversity along reasoning path
            by_doc: dict[str, list[Evidence]] = {}
            for r in records:
                prov = Provenance(
                    tier=SourceTier.TIER_1_DOCUMENT,
                    source_uri=r.get("doc_id", ""),
                    confidence=1.0,
                    verified=True,
                )
                ev = Evidence(
                    chunk_id=r["chunk_id"],
                    doc_id=r["doc_id"],
                    text=r["text"],
                    score=0.95,
                    retrieval_method="graph",
                    provenance=prov,
                )
                by_doc.setdefault(ev.doc_id, []).append(ev)

            # Round-robin across documents to guarantee multi-document representation in top-k
            while len(evidence_list) < top_k and any(by_doc.values()):
                for doc_id in list(by_doc.keys()):
                    if by_doc[doc_id]:
                        evidence_list.append(by_doc[doc_id].pop(0))
                        if len(evidence_list) >= top_k:
                            break

        return evidence_list

    @timed_async_stage("neo4j")
    async def search_entities(
        self,
        query: str,
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[dict[str, Any]]:
        """Search ACL-permitted entities matching the query string in Neo4j."""
        criteria = self._criteria(filter_criteria)
        entity_pred, params = criteria.to_cypher_predicate("e")
        cypher = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($q)
          AND {entity_pred}
        RETURN e.id AS id, e.name AS name, e.entity_type AS type
        LIMIT $limit
        """
        async with self.driver.session(database=get_settings().NEO4J_DATABASE) as session:
            res = await session.run(cypher, q=query.strip(), limit=top_k, **params)
            return await res.data()

    @timed_async_stage("entity_seeds")
    async def search_entity_seeds(
        self,
        query: str,
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[dict[str, Any]]:
        """Find canonical entity seeds from the query via the entity vector index.

        Uses deterministic extraction on the Ask path (never GLiNER) and keeps
        the search inside the caller's owner scope unless the caller is admin.
        """
        from app.indexing.qdrant_indexer import EntityVectorIndex
        from app.ingestion.entity_resolution import type_group
        from app.ingestion.extraction import EntityRelationExtractor

        criteria = self._criteria(filter_criteria)
        mentions = EntityRelationExtractor.extract_from_text(query).entities
        if not mentions:
            return []

        owns_index = self._entity_index is None
        index = self._entity_index or EntityVectorIndex()
        owner_user_id = None if criteria.is_admin else criteria.owner_user_id
        threshold = get_settings().ENTITY_SEED_MIN_COSINE
        seeds: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            for mention in mentions[:top_k]:
                candidates = await index.search_similar(
                    name=mention.name,
                    entity_type=mention.entity_type,
                    type_group=type_group(mention.entity_type),
                    owner_user_id=owner_user_id,
                    limit=top_k,
                    threshold=threshold,
                )
                for candidate in candidates:
                    entity_id = str(candidate.get("entity_id") or "")
                    if not entity_id or entity_id in seen:
                        continue
                    seen.add(entity_id)
                    seed = dict(candidate)
                    seed.setdefault("name", mention.name)
                    seed["_seed"] = mention.name
                    seeds.append(seed)
                    if len(seeds) >= top_k:
                        return seeds
        finally:
            if owns_index:
                await index.close()
        return seeds

    async def close(self) -> None:
        await self.driver.close()

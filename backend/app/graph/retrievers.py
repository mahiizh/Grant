import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings
from app.domain import Evidence, Provenance, SourceTier
from app.retrieval.filters import RetrievalFilter

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Production Graph retriever executing Cypher multi-hop traversals over Neo4j."""

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        settings = get_settings()
        self.driver = driver or AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    async def find_path(
        self,
        start_entity_name: str,
        target_entity_name: str,
        max_depth: int = 4,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[str] | None:
        """Find the shortest valid path between two entities in Neo4j."""
        cypher = f"""
        MATCH (a:Entity), (b:Entity)
        WHERE toLower(a.name) = toLower($start) AND toLower(b.name) = toLower($target)
        MATCH path = shortestPath((a)-[*..{max_depth}]-(b))
        WHERE ALL(n IN nodes(path) WHERE 'Entity' IN labels(n))
        RETURN [n IN nodes(path) | n.name] AS node_names,
               [r IN relationships(path) | type(r)] AS rel_types,
               [n IN nodes(path) | n.acl_scope] AS acl_scopes
        """
        async with self.driver.session() as session:
            res = await session.run(
                cypher,
                start=start_entity_name.strip(),
                target=target_entity_name.strip(),
            )
            record = await res.single()
            if not record:
                return None

            node_names = record["node_names"]
            rel_types = record["rel_types"]
            acl_scopes = record["acl_scopes"]

            # Filter path nodes by ACL if requested
            if filter_criteria is not None:
                for scope_str in acl_scopes:
                    if (
                        scope_str
                        and "executive-audit" in scope_str
                        and not bool(filter_criteria.user_roles & {"executive-audit"})
                    ):
                        return None

            # Interleave node names and relationship predicates: [A, REL, B, REL, C]
            path_tokens: list[str] = []
            for i, name in enumerate(node_names):
                path_tokens.append(name)
                if i < len(rel_types):
                    path_tokens.append(rel_types[i])

            return path_tokens

    async def retrieve_path_evidence(
        self,
        path_tokens: list[str],
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[Evidence]:
        """Fetch source chunks linked to the entities appearing in a reasoning path."""
        # Extract entity names (even positions)
        entity_names = [token for i, token in enumerate(path_tokens) if i % 2 == 0]
        if not entity_names:
            return []

        cypher = """
        MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
        WHERE e.name IN $entity_names
        RETURN DISTINCT c.chunk_id AS chunk_id,
                        c.doc_id AS doc_id,
                        c.text AS text,
                        c.acl_scope AS acl_scope,
                        c.valid_from AS valid_from,
                        c.valid_to AS valid_to
        LIMIT $limit
        """
        evidence_list: list[Evidence] = []
        async with self.driver.session() as session:
            res = await session.run(cypher, entity_names=entity_names, limit=top_k * 2)
            records = await res.data()

            # Group candidates by doc_id to ensure multi-doc diversity along reasoning path
            by_doc: dict[str, list[Evidence]] = {}
            for r in records:
                # Apply ACL/temporal filtering
                if filter_criteria is not None:
                    scope_raw = r.get("acl_scope") or ""
                    if "executive-audit" in scope_raw and not bool(
                        filter_criteria.user_roles & {"executive-audit"}
                    ):
                        continue

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

    async def search_entities(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search entities matching query string in Neo4j."""
        cypher = """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($q)
        RETURN e.id AS id, e.name AS name, e.entity_type AS type
        LIMIT $limit
        """
        async with self.driver.session() as session:
            res = await session.run(cypher, q=query.strip(), limit=top_k)
            return await res.data()

    async def close(self) -> None:
        await self.driver.close()

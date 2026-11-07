import json
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Neo4jIndexer:
    """Production Neo4j indexer managing knowledge graph nodes, edges, and chunks."""

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        settings = get_settings()
        self.uri = settings.NEO4J_URI
        self.auth = (settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        self.driver = driver or AsyncGraphDatabase.driver(self.uri, auth=self.auth)

    async def merge_node(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Idempotently create or update an Entity node in Neo4j."""
        cypher = """
        MERGE (n:Entity {id: $entity_id})
        SET n.name = $name,
            n.entity_type = $entity_type,
            n.acl_scope = $acl_scope,
            n.valid_from = $valid_from,
            n.valid_to = $valid_to,
            n.doc_id = $doc_id
        """
        props = properties or {}
        temp = temporal or {}
        async with self.driver.session() as session:
            await session.run(
                cypher,
                entity_id=entity_id,
                name=name,
                entity_type=entity_type,
                acl_scope=json.dumps(acl_scope or {}),
                valid_from=temp.get("valid_from", "1970-01-01T00:00:00Z"),
                valid_to=temp.get("valid_to"),
                doc_id=props.get("doc_id", ""),
            )

    async def merge_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Idempotently create or update a relationship edge between two entities."""
        rel_type_clean = "".join(c if c.isalnum() else "_" for c in relation_type).upper() or "RELATES_TO"
        cypher = f"""
        MERGE (a:Entity {{id: $source_id}})
        MERGE (b:Entity {{id: $target_id}})
        MERGE (a)-[r:{rel_type_clean}]->(b)
        SET r.relation_type = $relation_type,
            r.acl_scope = $acl_scope,
            r.valid_from = $valid_from,
            r.valid_to = $valid_to,
            r.doc_id = $doc_id
        RETURN elementId(r) AS rel_id
        """
        temp = temporal or {}
        props = properties or {}
        async with self.driver.session() as session:
            res = await session.run(
                cypher,
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                acl_scope=json.dumps(acl_scope or {}),
                valid_from=temp.get("valid_from", "1970-01-01T00:00:00Z"),
                valid_to=temp.get("valid_to"),
                doc_id=props.get("doc_id", ""),
            )
            record = await res.single()
            return str(record["rel_id"]) if record else f"{source_id}-{relation_type}->{target_id}"

    async def merge_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
    ) -> None:
        """Idempotently create or update a Chunk node in Neo4j."""
        cypher = """
        MERGE (c:Chunk {chunk_id: $chunk_id})
        SET c.doc_id = $doc_id,
            c.text = $text,
            c.acl_scope = $acl_scope,
            c.valid_from = $valid_from,
            c.valid_to = $valid_to
        """
        temp = temporal or {}
        async with self.driver.session() as session:
            await session.run(
                cypher,
                chunk_id=chunk_id,
                doc_id=doc_id,
                text=text,
                acl_scope=json.dumps(acl_scope or {}),
                valid_from=temp.get("valid_from", "1970-01-01T00:00:00Z"),
                valid_to=temp.get("valid_to"),
            )

    async def link_chunk_entity(self, chunk_id: str, entity_id: str) -> None:
        """Connect a chunk to an entity it mentions."""
        cypher = """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        MATCH (e:Entity {id: $entity_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        async with self.driver.session() as session:
            await session.run(cypher, chunk_id=chunk_id, entity_id=entity_id)

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Remove chunks, entities, and isolated relations originating from doc_id."""
        cypher = """
        MATCH (c:Chunk {doc_id: $doc_id})
        DETACH DELETE c
        """
        async with self.driver.session() as session:
            res = await session.run(cypher, doc_id=doc_id)
            summary = await res.consume()
            deleted = summary.counters.nodes_deleted

            # Also delete entity nodes that were solely defined by this document
            entity_cypher = """
            MATCH (e:Entity {doc_id: $doc_id})
            DETACH DELETE e
            """
            res_e = await session.run(entity_cypher, doc_id=doc_id)
            sum_e = await res_e.consume()
            return deleted + sum_e.counters.nodes_deleted

    async def count_nodes(self) -> int:
        cypher = "MATCH (n:Entity) RETURN count(n) AS cnt"
        async with self.driver.session() as session:
            res = await session.run(cypher)
            rec = await res.single()
            return int(rec["cnt"]) if rec else 0

    async def count_edges(self) -> int:
        cypher = "MATCH ()-[r]->() RETURN count(r) AS cnt"
        async with self.driver.session() as session:
            res = await session.run(cypher)
            rec = await res.single()
            return int(rec["cnt"]) if rec else 0

    async def get_all_chunk_ids(self) -> set[str]:
        cypher = "MATCH (c:Chunk) RETURN c.chunk_id AS chunk_id"
        chunk_ids: set[str] = set()
        async with self.driver.session() as session:
            res = await session.run(cypher)
            records = await res.values()
            for row in records:
                if row and row[0]:
                    chunk_ids.add(str(row[0]))
        return chunk_ids

    async def close(self) -> None:
        await self.driver.close()

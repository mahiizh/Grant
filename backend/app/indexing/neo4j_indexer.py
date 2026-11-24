import json
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _acl_props(acl_scope: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten an ACL scope into scalar Neo4j properties for Cypher predicates.

    Missing scopes default to deny (``is_public=False``) rather than public.
    """
    scope = acl_scope or {}
    return {
        "acl_tenant_id": scope.get("tenant_id", "default"),
        "acl_is_public": bool(scope.get("is_public", False)),
        "acl_allowed_roles": list(scope.get("allowed_roles", []) or []),
        "acl_allowed_groups": list(scope.get("allowed_groups", []) or []),
    }


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
        """Idempotently create or update an Entity node in Neo4j, maintaining ACL scope unions."""
        cypher = """
        MERGE (n:Entity {id: $entity_id})
        ON CREATE SET
            n.name = $name,
            n.entity_type = $entity_type,
            n.acl_scope = $acl_scope,
            n.acl_tenant_id = $acl_tenant_id,
            n.acl_is_public = $acl_is_public,
            n.acl_allowed_roles = $acl_allowed_roles,
            n.acl_allowed_groups = $acl_allowed_groups,
            n.doc_ids = CASE WHEN $doc_id <> '' THEN [$doc_id] ELSE [] END,
            n.source_ids = CASE WHEN $source_id <> '' THEN [$source_id] ELSE [] END,
            n.owner_user_ids = CASE WHEN $owner_user_id <> '' THEN [$owner_user_id] ELSE [] END,
            n.valid_from = $valid_from,
            n.valid_to = $valid_to,
            n.doc_id = $doc_id,
            n.aliases = $aliases
        ON MATCH SET
            n.name = $name,
            n.entity_type = $entity_type,
            n.acl_tenant_id = $acl_tenant_id,
            n.acl_is_public = (coalesce(n.acl_is_public, false) OR $acl_is_public),
            n.acl_allowed_roles = [r IN coalesce(n.acl_allowed_roles, []) WHERE NOT r IN $acl_allowed_roles] + $acl_allowed_roles,
            n.acl_allowed_groups = [g IN coalesce(n.acl_allowed_groups, []) WHERE NOT g IN $acl_allowed_groups] + $acl_allowed_groups,
            n.doc_ids = CASE
                WHEN $doc_id <> '' AND NOT $doc_id IN coalesce(n.doc_ids, [])
                THEN coalesce(n.doc_ids, []) + [$doc_id]
                ELSE coalesce(n.doc_ids, [])
            END,
            n.source_ids = CASE
                WHEN $source_id <> '' AND NOT $source_id IN coalesce(n.source_ids, [])
                THEN coalesce(n.source_ids, []) + [$source_id]
                ELSE coalesce(n.source_ids, [])
            END,
            n.owner_user_ids = CASE
                WHEN $owner_user_id <> '' AND NOT $owner_user_id IN coalesce(n.owner_user_ids, [])
                THEN coalesce(n.owner_user_ids, []) + [$owner_user_id]
                ELSE coalesce(n.owner_user_ids, [])
            END,
            n.aliases = REDUCE(acc = coalesce(n.aliases, []), a IN $aliases | CASE WHEN a IN acc OR a = '' THEN acc ELSE acc + [a] END)
        """
        props = properties or {}
        temp = temporal or {}
        owner_user_id = str(props.get("owner_user_id", "") or "")
        source_id = str(props.get("source_id", props.get("doc_id", "")) or "")
        aliases = [str(a) for a in (props.get("aliases") or []) if str(a).strip()]
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
                source_id=source_id,
                owner_user_id=owner_user_id,
                aliases=aliases,
                **_acl_props(acl_scope),
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
        """Idempotently create or update a relationship edge between two entities carrying chunk ACL."""
        rel_type_clean = (
            "".join(c if c.isalnum() else "_" for c in relation_type).upper() or "RELATES_TO"
        )
        props = properties or {}
        chunk_id = props.get("chunk_id") or props.get("doc_id") or ""
        cypher = f"""
        MATCH (a:Entity {{id: $source_id}})
        MATCH (b:Entity {{id: $target_id}})
        MERGE (a)-[r:{rel_type_clean} {{chunk_id: $chunk_id}}]->(b)
        SET r.relation_type = $relation_type,
            r.acl_scope = $acl_scope,
            r.acl_tenant_id = $acl_tenant_id,
            r.acl_is_public = $acl_is_public,
            r.acl_allowed_roles = $acl_allowed_roles,
            r.acl_allowed_groups = $acl_allowed_groups,
            r.valid_from = $valid_from,
            r.valid_to = $valid_to,
            r.doc_id = $doc_id,
            r.chunk_id = $chunk_id,
            r.source_id = $source_ref,
            r.thread_id = $thread_id,
            r.message_id = $message_id,
            r.owner_user_id = $owner_user_id,
            r.source_kind = $source_kind
        RETURN elementId(r) AS rel_id
        """
        temp = temporal or {}
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
                chunk_id=chunk_id,
                source_ref=str(props.get("source_id", props.get("doc_id", "")) or ""),
                thread_id=str(props.get("thread_id", "") or ""),
                message_id=str(props.get("message_id", "") or ""),
                owner_user_id=str(props.get("owner_user_id", "") or ""),
                source_kind=str(props.get("source_kind", "document") or "document"),
                **_acl_props(acl_scope),
            )
            record = await res.single()
            if record:
                return str(record["rel_id"])
            logger.warning(
                "Skipped edge %s (%s)->(%s): endpoint entity missing; create entities via merge_node first",
                relation_type,
                source_id,
                target_id,
            )
            return ""

    async def merge_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        """Idempotently create or update a Chunk node in Neo4j."""
        cypher = """
        MERGE (c:Chunk {chunk_id: $chunk_id})
        SET c.doc_id = $doc_id,
            c.text = $text,
            c.owner_user_id = $owner_user_id,
            c.acl_scope = $acl_scope,
            c.acl_tenant_id = $acl_tenant_id,
            c.acl_is_public = $acl_is_public,
            c.acl_allowed_roles = $acl_allowed_roles,
            c.acl_allowed_groups = $acl_allowed_groups,
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
                owner_user_id=owner_user_id or "",
                acl_scope=json.dumps(acl_scope or {}),
                valid_from=temp.get("valid_from", "1970-01-01T00:00:00Z"),
                valid_to=temp.get("valid_to"),
                **_acl_props(acl_scope),
            )

    async def link_chunk_entity(self, chunk_id: str, entity_id: str) -> None:
        """Connect a chunk to an entity it mentions and recompute entity ACL from all linked chunks."""
        cypher = """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        MATCH (e:Entity {id: $entity_id})
        MERGE (c)-[:MENTIONS]->(e)
        WITH e
        MATCH (chk:Chunk)-[:MENTIONS]->(e)
        WITH e,
             collect(DISTINCT chk.doc_id) AS doc_ids,
             any(x IN collect(chk) WHERE coalesce(x.acl_is_public, false)) AS is_public,
             [x IN collect(chk) | coalesce(x.acl_allowed_roles, [])] AS all_roles,
             [x IN collect(chk) | coalesce(x.acl_allowed_groups, [])] AS all_groups
        SET e.doc_ids = doc_ids,
            e.acl_is_public = is_public,
            e.acl_allowed_roles = REDUCE(acc = [], r_list IN all_roles |
                acc + [r IN r_list WHERE NOT r IN acc]
            ),
            e.acl_allowed_groups = REDUCE(acc = [], g_list IN all_groups |
                acc + [g IN g_list WHERE NOT g IN acc]
            )
        """
        async with self.driver.session() as session:
            await session.run(cypher, chunk_id=chunk_id, entity_id=entity_id)

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Remove chunks, edges, and recompute or delete orphaned entities for doc_id."""
        async with self.driver.session() as session:
            # 1. Find all entities mentioned by chunks of this doc
            find_entities_cypher = """
            MATCH (c:Chunk {doc_id: $doc_id})-[:MENTIONS]->(e:Entity)
            RETURN DISTINCT e.id AS entity_id
            """
            res = await session.run(find_entities_cypher, doc_id=doc_id)
            records = await res.data()
            entity_ids = [record["entity_id"] for record in records]

            # 2. Delete edges originating from doc_id
            edge_cypher = """
            MATCH ()-[r]->()
            WHERE r.doc_id = $doc_id
            DELETE r
            """
            res_edge = await session.run(edge_cypher, doc_id=doc_id)
            sum_edge = await res_edge.consume()

            # 3. Delete chunks of doc_id
            chunk_cypher = """
            MATCH (c:Chunk {doc_id: $doc_id})
            DETACH DELETE c
            """
            res_c = await session.run(chunk_cypher, doc_id=doc_id)
            sum_c = await res_c.consume()
            deleted = sum_c.counters.nodes_deleted + sum_edge.counters.relationships_deleted

            # 4. Recompute or delete affected entities
            for eid in entity_ids:
                recompute_cypher = """
                MATCH (e:Entity {id: $entity_id})
                OPTIONAL MATCH (chk:Chunk)-[:MENTIONS]->(e)
                WITH e, collect(chk) AS remaining_chunks
                WHERE size(remaining_chunks) = 0
                DETACH DELETE e
                """
                await session.run(recompute_cypher, entity_id=eid)

                recompute_props_cypher = """
                MATCH (e:Entity {id: $entity_id})<-[:MENTIONS]-(chk:Chunk)
                WITH e,
                     collect(DISTINCT chk.doc_id) AS doc_ids,
                     any(x IN collect(chk) WHERE coalesce(x.acl_is_public, false)) AS is_public,
                     [x IN collect(chk) | coalesce(x.acl_allowed_roles, [])] AS all_roles,
                     [x IN collect(chk) | coalesce(x.acl_allowed_groups, [])] AS all_groups
                SET e.doc_ids = doc_ids,
                    e.acl_is_public = is_public,
                    e.acl_allowed_roles = REDUCE(acc = [], r_list IN all_roles |
                        acc + [r IN r_list WHERE NOT r IN acc]
                    ),
                    e.acl_allowed_groups = REDUCE(acc = [], g_list IN all_groups |
                        acc + [g IN g_list WHERE NOT g IN acc]
                    )
                """
                await session.run(recompute_props_cypher, entity_id=eid)

            # 5. Also delete entities solely created for doc_id that had no chunks
            entity_cypher = """
            MATCH (e:Entity {doc_id: $doc_id})
            WHERE NOT (e)<-[:MENTIONS]-(:Chunk)
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

    async def delete_chat_graph(
        self,
        source_id: str | None = None,
        thread_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> int:
        """Delete chat-sourced graph edges/nodes and remove orphaned entities."""
        if not source_id and not thread_id:
            return 0
        async with self.driver.session() as session:
            match_clause = "MATCH ()-[r]->() WHERE (r.source_kind = 'chat' OR r.source_id STARTS WITH 'chat:')"
            params: dict[str, Any] = {}
            if source_id:
                match_clause += " AND r.source_id = $source_id"
                params["source_id"] = source_id
            if thread_id:
                match_clause += " AND r.thread_id = $thread_id"
                params["thread_id"] = thread_id
            if owner_user_id:
                match_clause += " AND r.owner_user_id = $owner_user_id"
                params["owner_user_id"] = owner_user_id
            res = await session.run(
                match_clause
                + " WITH collect(DISTINCT startNode(r).id) + collect(DISTINCT endNode(r).id) AS ids, collect(r) AS rels "
                + " FOREACH (_ IN rels | DELETE _) RETURN ids",
                **params,
            )
            rec = await res.single()
            entity_ids = [str(e) for e in (rec["ids"] if rec and rec["ids"] else []) if e]

            # Remove source refs from entities; delete entity if no remaining sources/mentions/edges.
            for eid in set(entity_ids):
                await session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})
                    SET e.source_ids = [s IN coalesce(e.source_ids, []) WHERE s <> $source_id]
                    WITH e
                    OPTIONAL MATCH (e)-[r]-()
                    OPTIONAL MATCH (:Chunk)-[:MENTIONS]->(e)
                    WITH e, count(r) AS rel_count, count(*) AS mention_rows
                    WHERE rel_count = 0 AND mention_rows = 0 AND size(coalesce(e.source_ids, [])) = 0 AND size(coalesce(e.doc_ids, [])) = 0
                    DETACH DELETE e
                    """,
                    entity_id=eid,
                    source_id=source_id or "",
                )
            return len(set(entity_ids))

    async def close(self) -> None:
        await self.driver.close()

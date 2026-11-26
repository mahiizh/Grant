import json
import logging
from datetime import UTC, datetime
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores

logger = logging.getLogger(__name__)


def _ingested_at(value: str | None) -> str:
    """Return a caller-supplied ingestion timestamp or a fresh UTC timestamp."""
    return value or datetime.now(UTC).isoformat()


def _acl_props(acl_scope: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten an owner/shared ACL into scalar properties for Cypher predicates.

    Missing or legacy restricted scopes default to deny. Only legacy payloads
    explicitly marked public map to the modern public ACL.
    """
    scope = acl_scope or {}
    owner = str(scope.get("owner_user_id") or "")
    shared = str(scope.get("shared_scope") or "")
    legacy_restricted = any(
        scope.get(key) for key in ("tenant_id", "allowed_roles", "allowed_groups")
    )
    return {
        "acl_owner": owner,
        "acl_shared": shared,
        "acl_public": not owner
        and not shared
        and (scope.get("is_public") is True or not legacy_restricted),
    }


class Neo4jIndexer:
    """Production Neo4j indexer managing knowledge graph nodes, edges, and chunks."""

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        settings = get_settings()
        assert_writable_stores(settings)
        self.uri = settings.NEO4J_URI
        self.auth = (settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        self.database = settings.NEO4J_DATABASE
        self.driver = driver or AsyncGraphDatabase.driver(self.uri, auth=self.auth)

    async def merge_node(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        acl_scope: dict[str, Any] | None = None,
        ingested_at: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create or update an Entity node without widening ACLs on later mentions.

        Entity ACLs are recalculated from all linked chunks by
        :meth:`refresh_entity_props` after mention edges are synced.
        """
        cypher = """
        MERGE (n:Entity {id: $entity_id})
        ON CREATE SET
            n.name = $name,
            n.entity_type = $entity_type,
            n.acl_scope = $acl_scope,
            n.owner_user_id = $acl_owner,
            n.shared_scope = $acl_shared,
            n.is_public = $acl_public,
            n.doc_ids = CASE WHEN $doc_id <> '' THEN [$doc_id] ELSE [] END,
            n.source_ids = CASE WHEN $source_id <> '' THEN [$source_id] ELSE [] END,
            n.ingested_at = $ingested_at,
            n.doc_id = $doc_id,
            n.aliases = $aliases,
            n.source_kind = $source_kind,
            n.source_kinds = [$source_kind],
            n.url = $url
        ON MATCH SET
            n.name = $name,
            n.entity_type = $entity_type,
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
            n.aliases = REDUCE(acc = coalesce(n.aliases, []), a IN $aliases | CASE WHEN a IN acc OR a = '' THEN acc ELSE acc + [a] END),
            n.source_kinds = CASE
                WHEN $source_kind IN coalesce(n.source_kinds, [coalesce(n.source_kind, 'document')])
                THEN coalesce(n.source_kinds, [coalesce(n.source_kind, 'document')])
                ELSE coalesce(n.source_kinds, [coalesce(n.source_kind, 'document')]) + [$source_kind]
            END,
            n.url = CASE WHEN $url <> '' THEN $url ELSE coalesce(n.url, '') END
        """
        props = properties or {}
        owner_user_id = str(props.get("owner_user_id", "") or "")
        source_id = str(props.get("source_id", props.get("doc_id", "")) or "")
        aliases = [str(a) for a in (props.get("aliases") or []) if str(a).strip()]
        source_kind = str(props.get("source_kind", "document") or "document")
        url = str(props.get("url", "") or "")
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                entity_id=entity_id,
                name=name,
                entity_type=entity_type,
                acl_scope=json.dumps(acl_scope or {}),
                ingested_at=_ingested_at(ingested_at),
                doc_id=props.get("doc_id", ""),
                source_id=source_id,
                owner_user_id=owner_user_id,
                aliases=aliases,
                source_kind=source_kind,
                url=url,
                **_acl_props(acl_scope),
            )

    async def merge_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        acl_scope: dict[str, Any] | None = None,
        ingested_at: str | None = None,
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
            r.owner_user_id = $acl_owner,
            r.shared_scope = $acl_shared,
            r.is_public = $acl_public,
            r.ingested_at = $ingested_at,
            r.doc_id = $doc_id,
            r.chunk_id = $chunk_id,
            r.source_id = $source_ref,
            r.thread_id = $thread_id,
            r.message_id = $message_id,
            r.source_kind = $source_kind
        RETURN elementId(r) AS rel_id
        """
        async with self.driver.session(database=self.database) as session:
            res = await session.run(
                cypher,
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                acl_scope=json.dumps(acl_scope or {}),
                ingested_at=_ingested_at(ingested_at),
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
        ingested_at: str | None = None,
        owner_user_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Idempotently create or update a Chunk node in Neo4j."""
        cypher = """
        MERGE (c:Chunk {chunk_id: $chunk_id})
        SET c.doc_id = $doc_id,
            c.text = $text,
            c.owner_user_id = $acl_owner,
            c.shared_scope = $acl_shared,
            c.is_public = $acl_public,
            c.acl_scope = $acl_scope,
            c.ingested_at = $ingested_at,
            c.source_kind = $source_kind,
            c.url = $url,
            c.fetched_at = $fetched_at
        """
        props = properties or {}
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                chunk_id=chunk_id,
                doc_id=doc_id,
                text=text,
                owner_user_id=owner_user_id or "",
                acl_scope=json.dumps(acl_scope or {}),
                ingested_at=_ingested_at(ingested_at),
                source_kind=str(props.get("source_kind", "document") or "document"),
                url=str(props.get("url", "") or ""),
                fetched_at=props.get("fetched_at"),
                **_acl_props(acl_scope),
            )

    async def refresh_entity_props(self, entity_ids: list[str]) -> None:
        """Refresh source docs and deterministic ACLs for the given entities in one batch."""
        ids = list(dict.fromkeys(entity_ids))
        if not ids:
            return
        cypher = """
        UNWIND $entity_ids AS entity_id
        MATCH (e:Entity {id: entity_id})
        CALL (e) {
            MATCH (c:Chunk)-[:MENTIONS]->(e)
            WITH e, collect(DISTINCT coalesce(c.doc_id, '')) AS raw_doc_ids,
                 collect(DISTINCT coalesce(c.owner_user_id, '')) AS raw_owners,
                 collect(DISTINCT coalesce(c.shared_scope, '')) AS raw_shared,
                 collect(coalesce(c.is_public, false)) AS publics,
                 collect(DISTINCT coalesce(c.source_kind, 'document')) AS source_kinds
            WITH e, [d IN raw_doc_ids WHERE d <> ''] AS doc_ids,
                 [o IN raw_owners WHERE o <> ''] AS owners,
                 [s IN raw_shared WHERE s <> ''] AS shared,
                 all(pub IN publics WHERE pub) AS all_public,
                 source_kinds
            SET e.doc_ids = doc_ids,
                e.owner_user_id = CASE WHEN size(owners) > 0 THEN head(owners) ELSE '' END,
                e.shared_scope = CASE WHEN size(shared) > 0 THEN head(shared) ELSE '' END,
                e.is_public = size(owners) = 0 AND size(shared) = 0 AND all_public,
                e.source_kinds = source_kinds,
                e.source_kind = CASE WHEN 'web' IN source_kinds THEN 'web'
                                     ELSE coalesce(head(source_kinds), 'document') END
            RETURN count(*) AS refreshed
        }
        RETURN e.id AS id
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, entity_ids=ids)
            await result.consume()

    async def link_chunk_entity(self, chunk_id: str, entity_id: str) -> None:
        """Connect a chunk to an entity it mentions."""
        cypher = """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        MATCH (e:Entity {id: $entity_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, chunk_id=chunk_id, entity_id=entity_id)
            await result.consume()

    async def merge_chat_mention(
        self,
        *,
        message_id: str,
        source_id: str,
        thread_id: str,
        entity_id: str,
        acl_scope: dict[str, Any] | None,
        ingested_at: str | None,
        owner_user_id: str | None,
    ) -> None:
        """Persist the Message node and MENTIONS edge backing a chat entity mention."""
        cypher = """
        MERGE (m:Message {message_id: $message_id})
        SET m.id = $source_id,
            m.source_id = $source_id,
            m.thread_id = $thread_id,
            m.owner_user_id = $acl_owner,
            m.shared_scope = $acl_shared,
            m.is_public = $acl_public,
            m.acl_scope = $acl_scope,
            m.ingested_at = $ingested_at
        WITH m
        MATCH (e:Entity {id: $entity_id})
        MERGE (m)-[r:MENTIONS]->(e)
        SET r.source_id = $source_id,
            r.source_kind = 'chat',
            r.thread_id = $thread_id,
            r.owner_user_id = $acl_owner,
            r.shared_scope = $acl_shared,
            r.is_public = $acl_public
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                message_id=message_id,
                source_id=source_id,
                thread_id=thread_id,
                entity_id=entity_id,
                owner_user_id=owner_user_id or "",
                acl_scope=json.dumps(acl_scope or {}),
                ingested_at=_ingested_at(ingested_at),
                **_acl_props(acl_scope),
            )

    async def upsert_query_answer(
        self,
        *,
        query_id: str,
        answer_id: str,
        previous_query_id: str | None,
        thread_id: str | None,
        owner_user_id: str | None,
        raw_query: str,
        rewritten_query: str | None,
        answer: str,
        answer_policy: str,
        source_kind: str,
        is_abstention: bool,
        acl_scope: dict[str, Any] | None,
        ingested_at: str | None,
        query_entities: list[dict[str, Any]],
        answer_entities: list[dict[str, Any]],
        cites: list[dict[str, Any]],
        web_sources: list[dict[str, Any]],
    ) -> None:
        """Create Query/Answer nodes and their evidence and conversation edges."""
        acl = acl_scope or {}
        acl_json = json.dumps(acl)
        owner = owner_user_id or ""
        thread = thread_id or ""
        query_cypher = """
        MERGE (q:Query {id: $query_id})
        SET q.query_id = $query_id,
            q.raw_query = $raw_query,
            q.rewritten_query = $rewritten_query,
            q.answer_policy = $answer_policy,
            q.thread_id = $thread_id,
            q.owner_user_id = $acl_owner,
            q.shared_scope = $acl_shared,
            q.is_public = $acl_public,
            q.acl_scope = $acl_scope,
            q.ingested_at = $ingested_at
        MERGE (a:Answer {id: $answer_id})
        SET a.answer_id = $answer_id,
            a.content = $answer,
            a.source_kind = $source_kind,
            a.is_abstention = $is_abstention,
            a.web_sources = $web_sources,
            a.query_id = $query_id,
            a.thread_id = $thread_id,
            a.owner_user_id = $acl_owner,
            a.shared_scope = $acl_shared,
            a.is_public = $acl_public,
            a.acl_scope = $acl_scope,
            a.ingested_at = $ingested_at
        MERGE (q)-[:ANSWERS]->(a)
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                query_cypher,
                query_id=query_id,
                answer_id=answer_id,
                raw_query=raw_query,
                rewritten_query=rewritten_query or raw_query,
                answer=answer,
                answer_policy=answer_policy,
                source_kind=source_kind,
                is_abstention=bool(is_abstention),
                thread_id=thread,
                owner_user_id=owner,
                acl_scope=acl_json,
                ingested_at=_ingested_at(ingested_at),
                web_sources=json.dumps(web_sources or [], default=str),
                **_acl_props(acl),
            )

            for entities, node_cypher in (
                (
                    query_entities,
                    """
                    MATCH (q:Query {id: $node_id})
                    MATCH (e:Entity {id: $entity_id})
                    MERGE (q)-[r:MENTIONS]->(e)
                    SET r.source_id = $source_id,
                        r.source_kind = $relation_source_kind,
                        r.thread_id = $thread_id,
                        r.owner_user_id = $owner_user_id
                    """,
                ),
                (
                    answer_entities,
                    """
                    MATCH (a:Answer {id: $node_id})
                    MATCH (e:Entity {id: $entity_id})
                    MERGE (a)-[r:MENTIONS]->(e)
                    SET r.source_id = $source_id,
                        r.source_kind = $relation_source_kind,
                        r.thread_id = $thread_id,
                        r.owner_user_id = $owner_user_id
                    """,
                ),
            ):
                is_query = node_cypher.lstrip().startswith("MATCH (q:")
                node_id = query_id if is_query else answer_id
                source_id = f"chat:query:{query_id}" if is_query else f"chat:answer:{answer_id}"
                for entity in entities:
                    entity_id = entity.get("entity_id") or entity.get("name")
                    if not entity_id:
                        continue
                    await session.run(
                        node_cypher,
                        node_id=node_id,
                        entity_id=entity_id,
                        source_id=source_id,
                        relation_source_kind="query" if is_query else "answer",
                        thread_id=thread,
                        owner_user_id=owner,
                    )

            cites_cypher = """
            MATCH (a:Answer {id: $answer_id})
            MERGE (s:Source {id: $source_id})
            SET s.source_kind = $source_kind,
                s.url = $url
            MERGE (a)-[r:CITES]->(s)
            SET r.source_kind = $source_kind,
                r.thread_id = $thread_id,
                r.owner_user_id = $owner_user_id
            """
            for cite in cites:
                source_id = cite.get("source_id")
                if not source_id:
                    continue
                url = str(cite.get("url") or "")
                if not url and str(cite.get("source_kind")) == "web":
                    url = str(source_id)
                await session.run(
                    cites_cypher,
                    answer_id=answer_id,
                    source_id=str(source_id),
                    source_kind=str(cite.get("source_kind", "document")),
                    url=url,
                    thread_id=thread,
                    owner_user_id=owner,
                )

            if previous_query_id:
                await session.run(
                    """
                    MATCH (prev:Query {id: $previous_query_id})
                    MATCH (q:Query {id: $query_id})
                    MERGE (prev)-[:NEXT]->(q)
                    """,
                    previous_query_id=previous_query_id,
                    query_id=query_id,
                )

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Remove chunks, edges, and recompute or delete orphaned entities for doc_id."""
        async with self.driver.session(database=self.database) as session:
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

            # 5. Also delete entities solely created for doc_id that had no chunks
            entity_cypher = """
            MATCH (e:Entity {doc_id: $doc_id})
            WHERE NOT (e)<-[:MENTIONS]-(:Chunk)
            DETACH DELETE e
            """
            res_e = await session.run(entity_cypher, doc_id=doc_id)
            sum_e = await res_e.consume()
            total_deleted = deleted + sum_e.counters.nodes_deleted

        await self.refresh_entity_props(entity_ids)
        return total_deleted

    async def count_nodes(self) -> int:
        cypher = "MATCH (n:Entity) RETURN count(n) AS cnt"
        async with self.driver.session(database=self.database) as session:
            res = await session.run(cypher)
            rec = await res.single()
            return int(rec["cnt"]) if rec else 0

    async def count_edges(self) -> int:
        cypher = "MATCH ()-[r]->() RETURN count(r) AS cnt"
        async with self.driver.session(database=self.database) as session:
            res = await session.run(cypher)
            rec = await res.single()
            return int(rec["cnt"]) if rec else 0

    async def get_all_chunk_ids(self) -> set[str]:
        cypher = "MATCH (c:Chunk) RETURN c.chunk_id AS chunk_id"
        chunk_ids: set[str] = set()
        async with self.driver.session(database=self.database) as session:
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
        async with self.driver.session(database=self.database) as session:
            match_clause = (
                "MATCH ()-[r]->() WHERE (r.source_kind = 'chat' OR r.source_id STARTS WITH 'chat:')"
            )
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

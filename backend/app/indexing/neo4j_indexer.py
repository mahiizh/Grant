import json
import logging
from collections.abc import Iterable
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
    """Neo4j indexer for the connected Document/Entity/Query/Answer/Message graph.

    Chunk text and chunk↔entity links are intentionally absent: chunk payloads
    live in Qdrant and chunk links in Postgres ``entity_mentions``.
    """

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

        Entity ACLs are recalculated from linked Document nodes by
        :meth:`refresh_entity_props` after document edges are synced.
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
        """Idempotently create or update a relationship edge between two entities."""
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

    async def merge_document(
        self,
        *,
        doc_id: str,
        title: str,
        acl_scope: dict[str, Any] | None,
        source_kind: str,
        url: str | None,
        fetched_at: str | None,
        content_hash: str | None = None,
        ingested_at: str | None = None,
    ) -> None:
        """Create or update the Document node that owns document entity links."""
        cypher = """
        MERGE (d:Document {doc_id: $doc_id})
        SET d.title = $title,
            d.owner_user_id = $acl_owner,
            d.shared_scope = $acl_shared,
            d.is_public = $acl_public,
            d.acl_scope = $acl_scope,
            d.source_kind = $source_kind,
            d.url = $url,
            d.fetched_at = $fetched_at,
            d.content_hash = $content_hash,
            d.ingested_at = $ingested_at
        """
        async with self.driver.session(database=self.database) as session:
            await session.run(
                cypher,
                doc_id=doc_id,
                title=title or doc_id,
                acl_scope=json.dumps(acl_scope or {}),
                source_kind=source_kind or "document",
                url=url or "",
                fetched_at=fetched_at,
                content_hash=content_hash or "",
                ingested_at=_ingested_at(ingested_at),
                **_acl_props(acl_scope),
            )

    async def sync_document_graph(
        self,
        *,
        doc_id: str,
        acl_scope: dict[str, Any] | None,
        entity_counts: dict[str, int],
        cooccurrence_counts: dict[tuple[str, str], int],
        source_kind: str = "document",
        ingested_at: str | None = None,
    ) -> None:
        """Replace a document's aggregated MENTIONS and CO_OCCURS edges."""
        acl_json = json.dumps(acl_scope or {})
        acl_props = _acl_props(acl_scope)
        timestamp = _ingested_at(ingested_at)
        async with self.driver.session(database=self.database) as session:
            await session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})-[r:MENTIONS]->(:Entity)
                DELETE r
                WITH d
                OPTIONAL MATCH ()-[r:CO_OCCURS {doc_id: $doc_id}]->()
                DELETE r
                """,
                doc_id=doc_id,
            )
            for entity_id, count in entity_counts.items():
                await session.run(
                    """
                    MATCH (d:Document {doc_id: $doc_id})
                    MERGE (e:Entity {id: $entity_id})
                    ON CREATE SET
                        e.name = $entity_id,
                        e.entity_type = 'Concept',
                        e.aliases = [],
                        e.doc_ids = [],
                        e.source_ids = [],
                        e.source_kinds = []
                    MERGE (d)-[r:MENTIONS]->(e)
                    SET r.count = $count,
                        r.acl_scope = $acl_scope,
                        r.owner_user_id = $acl_owner,
                        r.shared_scope = $acl_shared,
                        r.is_public = $acl_public,
                        r.ingested_at = $ingested_at,
                        r.source_kind = $source_kind
                    """,
                    doc_id=doc_id,
                    entity_id=entity_id,
                    count=int(count),
                    acl_scope=acl_json,
                    ingested_at=timestamp,
                    source_kind=source_kind or "document",
                    **acl_props,
                )
            for (source_id, target_id), count in cooccurrence_counts.items():
                await session.run(
                    """
                    MERGE (a:Entity {id: $source_id})
                    ON CREATE SET
                        a.name = $source_id,
                        a.entity_type = 'Concept',
                        a.aliases = [],
                        a.doc_ids = [],
                        a.source_ids = [],
                        a.source_kinds = []
                    MERGE (b:Entity {id: $target_id})
                    ON CREATE SET
                        b.name = $target_id,
                        b.entity_type = 'Concept',
                        b.aliases = [],
                        b.doc_ids = [],
                        b.source_ids = [],
                        b.source_kinds = []
                    MERGE (a)-[r:CO_OCCURS {doc_id: $doc_id}]->(b)
                    SET r.count = $count,
                        r.doc_id = $doc_id,
                        r.acl_scope = $acl_scope,
                        r.owner_user_id = $acl_owner,
                        r.shared_scope = $acl_shared,
                        r.is_public = $acl_public,
                        r.ingested_at = $ingested_at,
                        r.source_kind = $source_kind
                    """,
                    doc_id=doc_id,
                    source_id=source_id,
                    target_id=target_id,
                    count=int(count),
                    acl_scope=acl_json,
                    ingested_at=timestamp,
                    source_kind=source_kind or "document",
                    **acl_props,
                )

    async def refresh_entity_props(self, entity_ids: Iterable[str]) -> None:
        """Recompute source documents and ACLs from Document-MENTIONS edges."""
        ids = list(dict.fromkeys(entity_ids))
        if not ids:
            return
        cypher = """
        UNWIND $entity_ids AS entity_id
        MATCH (e:Entity {id: entity_id})
        OPTIONAL MATCH (d:Document)-[:MENTIONS]->(e)
        WITH e,
             [x IN collect(DISTINCT coalesce(d.doc_id, '')) WHERE x <> ''] AS doc_ids,
             [x IN collect(DISTINCT coalesce(d.owner_user_id, '')) WHERE x <> ''] AS owners,
             [x IN collect(DISTINCT coalesce(d.shared_scope, '')) WHERE x <> ''] AS shared,
             collect(coalesce(d.is_public, false)) AS publics,
             [x IN collect(DISTINCT coalesce(d.source_kind, 'document')) WHERE x <> ''] AS source_kinds
        SET e.doc_ids = doc_ids,
            e.owner_user_id = CASE WHEN size(owners) > 0 THEN head(owners) ELSE '' END,
            e.shared_scope = CASE WHEN size(shared) > 0 THEN head(shared) ELSE '' END,
            e.is_public = size(owners) = 0 AND size(shared) = 0 AND all(pub IN publics WHERE pub),
            e.source_kinds = source_kinds,
            e.source_kind = CASE WHEN 'web' IN source_kinds THEN 'web'
                                 ELSE coalesce(head(source_kinds), 'document') END
        RETURN e.id AS id
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(cypher, entity_ids=ids)
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
        acl = dict(acl_scope or {})
        if owner_user_id and not acl.get("owner_user_id"):
            acl["owner_user_id"] = owner_user_id
        acl_json = json.dumps(acl)
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
        MERGE (q)-[:ANSWERED_BY]->(a)
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
                    MERGE (q)-[r:ABOUT]->(e)
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
                        owner_user_id=owner_user_id or "",
                    )

            cites_cypher = """
            MATCH (a:Answer {id: $answer_id})
            MERGE (d:Document {doc_id: $source_id})
            ON CREATE SET
                d.title = $source_id,
                d.owner_user_id = $acl_owner,
                d.shared_scope = $acl_shared,
                d.is_public = $acl_public,
                d.source_kind = $source_kind,
                d.url = $url
            MERGE (a)-[r:CITES]->(d)
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
                    owner_user_id=owner_user_id or "",
                    acl_scope=acl_json,
                    **_acl_props(acl),
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
        """Remove a Document node, its aggregated edges, and orphaned entities."""
        async with self.driver.session(database=self.database) as session:
            res = await session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})-[:MENTIONS]->(e:Entity)
                RETURN DISTINCT e.id AS entity_id
                """,
                doc_id=doc_id,
            )
            records = await res.data()
            entity_ids = [str(record["entity_id"]) for record in records if record.get("entity_id")]

            # Separate statements: a document with no entities has no CO_OCCURS
            # edges, and a chained MATCH would skip the Document deletion below.
            cooccur_res = await session.run(
                """
                MATCH ()-[r:CO_OCCURS {doc_id: $doc_id}]->()
                WITH collect(r) AS rels
                FOREACH (rel IN rels | DELETE rel)
                RETURN size(rels) AS cnt
                """,
                doc_id=doc_id,
            )
            cooccur_record = await cooccur_res.single()

            mention_res = await session.run(
                """
                MATCH (:Document {doc_id: $doc_id})-[r:MENTIONS]->(:Entity)
                WITH collect(r) AS rels
                FOREACH (rel IN rels | DELETE rel)
                RETURN size(rels) AS cnt
                """,
                doc_id=doc_id,
            )
            mention_record = await mention_res.single()

            document_res = await session.run(
                """
                MATCH (d:Document {doc_id: $doc_id})
                WITH collect(d) AS docs
                FOREACH (doc IN docs | DETACH DELETE doc)
                RETURN size(docs) AS cnt
                """,
                doc_id=doc_id,
            )
            document_record = await document_res.single()

            deleted = (
                int((cooccur_record or {}).get("cnt") or 0)
                + int((mention_record or {}).get("cnt") or 0)
                + int((document_record or {}).get("cnt") or 0)
            )

            for entity_id in entity_ids:
                await session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})
                    WHERE NOT (e)--()
                    DETACH DELETE e
                    """,
                    entity_id=entity_id,
                )

        await self.refresh_entity_props(entity_ids)
        return deleted

    async def count_nodes(self) -> int:
        cypher = "MATCH (n) RETURN count(n) AS cnt"
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

    async def get_all_document_ids(self) -> set[str]:
        cypher = "MATCH (d:Document) RETURN d.doc_id AS doc_id"
        doc_ids: set[str] = set()
        async with self.driver.session(database=self.database) as session:
            res = await session.run(cypher)
            for row in await res.values():
                if row and row[0]:
                    doc_ids.add(str(row[0]))
        return doc_ids

    async def document_exists(self, doc_id: str) -> bool:
        cypher = "MATCH (d:Document {doc_id: $doc_id}) RETURN count(d) AS cnt"
        async with self.driver.session(database=self.database) as session:
            res = await session.run(cypher, doc_id=doc_id)
            rec = await res.single()
            return bool(rec and int(rec["cnt"]) > 0)

    async def document_graph_exists(self, doc_id: str) -> bool:
        """True when a Document node or its CO_OCCURS edge payloads remain."""
        if await self.document_exists(doc_id):
            return True
        async with self.driver.session(database=self.database) as session:
            res = await session.run(
                "MATCH ()-[r:CO_OCCURS {doc_id: $doc_id}]->() RETURN count(r) AS cnt",
                doc_id=doc_id,
            )
            rec = await res.single()
            return bool(rec and int(rec["cnt"]) > 0)

    async def get_all_entity_ids(self) -> set[str]:
        cypher = "MATCH (e:Entity) RETURN e.id AS id"
        entity_ids: set[str] = set()
        async with self.driver.session(database=self.database) as session:
            res = await session.run(cypher)
            for row in await res.values():
                if row and row[0]:
                    entity_ids.add(str(row[0]))
        return entity_ids

    async def delete_orphan_entities(self) -> int:
        """Delete entities with no Postgres-equivalent graph edges left."""
        async with self.driver.session(database=self.database) as session:
            res = await session.run(
                """
                MATCH (e:Entity)
                WHERE NOT (e)--()
                DETACH DELETE e
                RETURN count(e) AS deleted
                """
            )
            rec = await res.single()
            return int(rec["deleted"]) if rec else 0

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

            for eid in set(entity_ids):
                await session.run(
                    """
                    MATCH (e:Entity {id: $entity_id})
                    SET e.source_ids = [s IN coalesce(e.source_ids, []) WHERE s <> $source_id]
                    WITH e
                    WHERE NOT (e)-[:MENTIONS]-(:Document)
                      AND NOT (e)<-[:ABOUT]-(:Query)
                      AND NOT (e)<-[:MENTIONS]-(:Answer)
                      AND NOT (e)<-[:MENTIONS]-(:Message)
                    DETACH DELETE e
                    """,
                    entity_id=eid,
                    source_id=source_id or "",
                )
            return len(set(entity_ids))

    async def close(self) -> None:
        await self.driver.close()

from collections.abc import Iterable
from typing import Any


class FakeQdrantIndexer:
    """In-memory Qdrant indexer fake for tests."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    async def upsert_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        payload: dict[str, Any],
        vector: list[float] | None = None,
    ) -> None:
        normalized_payload = dict(payload)
        normalized_payload.setdefault("chunk_id", chunk_id)
        normalized_payload.setdefault("doc_id", doc_id)
        normalized_payload.setdefault("text", text)
        self._store[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "vector": vector or [0.0] * 384,
            "payload": normalized_payload,
        }

    async def delete_chunk(self, chunk_id: str) -> bool:
        if chunk_id in self._store:
            del self._store[chunk_id]
            return True
        return False

    async def delete_by_doc_id(self, doc_id: str) -> int:
        to_delete = [
            chunk_id
            for chunk_id, record in self._store.items()
            if record.get("doc_id") == doc_id
        ]
        for chunk_id in to_delete:
            del self._store[chunk_id]
        return len(to_delete)

    async def get_all_chunk_ids(self) -> set[str]:
        return set(self._store)

    async def get_chunks(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch payloads by chunk id, matching the production graph-read path."""
        return {
            str(chunk_id): dict(self._store[str(chunk_id)]["payload"])
            for chunk_id in chunk_ids
            if str(chunk_id) in self._store
        }

    async def get_chunks_by_doc_id(self, doc_id: str) -> dict[str, dict[str, Any]]:
        return {
            chunk_id: dict(record["payload"])
            for chunk_id, record in self._store.items()
            if record.get("doc_id") == doc_id
        }

    async def get_all_entity_ids(self) -> set[str]:
        return set()

    def count(self) -> int:
        return len(self._store)

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        return self._store.get(chunk_id)

    async def close(self) -> None:
        return None


class FakeNeo4jIndexer:
    """In-memory fake of the slimmed Document/Entity/Query/Answer/Message graph.

    There are deliberately no Chunk nodes or chunk→entity edges: those live in
    Qdrant payloads and Postgres ``entity_mentions`` respectively.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._documents: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}
        self._entity_to_docs: dict[str, set[str]] = {}
        self._doc_entities: dict[str, set[str]] = {}
        self._queries: dict[str, dict[str, Any]] = {}
        self._answers: dict[str, dict[str, Any]] = {}
        self._messages: dict[str, dict[str, Any]] = {}
        self._query_answer_edges: list[tuple[str, str]] = []
        self._next_edges: list[tuple[str, str]] = []

    @staticmethod
    def _edge_key(
        source_id: str,
        relation_type: str,
        target_id: str,
        suffix: str = "",
    ) -> str:
        return f"{source_id}-[{relation_type}{suffix}]->{target_id}"

    def _entity_has_edge(self, entity_id: str) -> bool:
        return any(
            edge.get("source_id") == entity_id or edge.get("target_id") == entity_id
            for edge in self._edges.values()
        )

    def _delete_orphan_entities(self) -> int:
        deleted = 0
        for entity_id in list(self._nodes):
            if self._entity_to_docs.get(entity_id):
                continue
            if self._entity_has_edge(entity_id):
                continue
            del self._nodes[entity_id]
            self._entity_to_docs.pop(entity_id, None)
            deleted += 1
        return deleted

    def _recompute_entity_acl(self, entity_id: str) -> None:
        if entity_id not in self._nodes:
            return
        doc_ids = self._entity_to_docs.get(entity_id, set())
        if not doc_ids:
            # Chat-only entities keep the ACL assigned when they were created;
            # chat links must never widen a document-scoped entity.
            return
        owners: set[str] = set()
        shared: set[str] = set()
        public = True
        for doc_id in doc_ids:
            doc = self._documents.get(doc_id, {})
            scope = doc.get("acl_scope", {})
            owner = doc.get("owner_user_id") or scope.get("owner_user_id")
            doc_shared = doc.get("shared_scope") or scope.get("shared_scope")
            if owner:
                owners.add(str(owner))
            if doc_shared:
                shared.add(str(doc_shared))
            if owner or doc_shared:
                public = False
        node = self._nodes[entity_id]
        node["doc_ids"] = sorted(doc_ids)
        node["acl_scope"] = {
            "owner_user_id": sorted(owners)[0] if owners else None,
            "shared_scope": sorted(shared)[0] if shared else None,
        }
        node["acl_owner_user_id"] = node["acl_scope"]["owner_user_id"] or ""
        node["acl_shared_scope"] = node["acl_scope"]["shared_scope"] or ""
        node["acl_is_public"] = public
        node["owner_user_ids"] = sorted(owners)

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
        scope = acl_scope or {}
        self._documents[doc_id] = {
            "doc_id": doc_id,
            "title": title or doc_id,
            "acl_scope": scope,
            "owner_user_id": scope.get("owner_user_id"),
            "shared_scope": scope.get("shared_scope"),
            "source_kind": source_kind,
            "url": url,
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "ingested_at": ingested_at,
        }

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
        scope = acl_scope or {}
        for edge_id, edge in list(self._edges.items()):
            is_doc_mention = (
                edge.get("relation_type") == "MENTIONS"
                and edge.get("source_id") == doc_id
                and edge.get("source_kind") != "chat"
            )
            is_doc_cooccur = (
                edge.get("relation_type") == "CO_OCCURS"
                and edge.get("doc_id") == doc_id
            )
            if is_doc_mention or is_doc_cooccur:
                del self._edges[edge_id]

        for entity_id in self._doc_entities.get(doc_id, set()):
            self._entity_to_docs.get(entity_id, set()).discard(doc_id)
        self._doc_entities[doc_id] = set(entity_counts)

        for entity_id, count in entity_counts.items():
            self._entity_to_docs.setdefault(entity_id, set()).add(doc_id)
            edge_id = self._edge_key(doc_id, "MENTIONS", entity_id)
            self._edges[edge_id] = {
                "edge_id": edge_id,
                "source_id": doc_id,
                "target_id": entity_id,
                "relation_type": "MENTIONS",
                "acl_scope": scope,
                "ingested_at": ingested_at,
                "properties": {"count": count, "source_kind": source_kind},
                "count": count,
                "doc_id": doc_id,
                "source_kind": source_kind,
            }
        for (source_id, target_id), count in cooccurrence_counts.items():
            edge_id = self._edge_key(
                source_id, "CO_OCCURS", target_id, suffix=f":{doc_id}"
            )
            self._edges[edge_id] = {
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": "CO_OCCURS",
                "acl_scope": scope,
                "ingested_at": ingested_at,
                "properties": {"count": count, "doc_id": doc_id, "source_kind": source_kind},
                "count": count,
                "doc_id": doc_id,
                "source_kind": source_kind,
            }
        for entity_id in entity_counts:
            self._recompute_entity_acl(entity_id)

    async def refresh_entity_props(self, entity_ids: Iterable[str]) -> None:
        for entity_id in entity_ids:
            self._recompute_entity_acl(str(entity_id))

    async def merge_node(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        acl_scope: dict[str, Any] | None = None,
        ingested_at: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        scope = acl_scope or {}
        props = dict(properties or {})
        doc_id = str(props.get("doc_id", "") or "")
        source_id = str(props.get("source_id", "") or "")
        owner = scope.get("owner_user_id") or None
        shared = scope.get("shared_scope") or None
        is_public = bool(scope.get("is_public", not owner and not shared))
        entity_id = str(entity_id)
        if entity_id in self._nodes:
            existing = self._nodes[entity_id]
            existing["name"] = name
            existing["entity_type"] = entity_type
            for key, value in (
                ("doc_id", doc_id),
                ("source_id", source_id),
            ):
                if value and value not in existing.setdefault("doc_ids" if key == "doc_id" else "source_ids", []):
                    existing["doc_ids" if key == "doc_id" else "source_ids"].append(value)
            aliases = [str(alias) for alias in props.get("aliases", []) if alias]
            existing_aliases = existing.setdefault("aliases", [])
            for alias in aliases:
                if alias not in existing_aliases:
                    existing_aliases.append(alias)
            existing["properties"] = {**existing.get("properties", {}), **props}
            return

        self._nodes[entity_id] = {
            "entity_id": entity_id,
            "id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "aliases": [str(alias) for alias in props.get("aliases", []) if alias],
            "acl_scope": {"owner_user_id": owner, "shared_scope": shared},
            "acl_owner_user_id": owner or "",
            "acl_shared_scope": shared or "",
            "acl_is_public": is_public,
            "owner_user_ids": [owner] if owner else [],
            "doc_ids": [doc_id] if doc_id else [],
            "source_ids": [source_id] if source_id else [],
            "ingested_at": ingested_at,
            "properties": props,
        }

    async def merge_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        acl_scope: dict[str, Any] | None = None,
        ingested_at: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        props = dict(properties or {})
        relation = str(relation_type).upper()
        chunk_id = str(props.get("chunk_id") or props.get("doc_id") or "")
        edge_id = self._edge_key(source_id, relation, target_id, suffix=f":{chunk_id}")
        self._edges[edge_id] = {
            "edge_id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation,
            "acl_scope": acl_scope or {},
            "ingested_at": ingested_at,
            "properties": props,
            "chunk_id": chunk_id,
            "doc_id": props.get("doc_id", ""),
            "source_id": props.get("source_id", source_id),
        }
        return edge_id

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
        scope = acl_scope or {}
        self._messages[message_id] = {
            "message_id": message_id,
            "source_id": source_id,
            "thread_id": thread_id,
            "owner_user_id": owner_user_id,
            "acl_scope": scope,
            "ingested_at": ingested_at,
        }
        edge_id = self._edge_key(
            message_id, "MENTIONS", entity_id, suffix=f":{source_id}"
        )
        self._edges[edge_id] = {
            "edge_id": edge_id,
            "source_id": message_id,
            "target_id": entity_id,
            "relation_type": "MENTIONS",
            "source_kind": "chat",
            "source_id": source_id,
            "thread_id": thread_id,
            "acl_scope": scope,
        }

    async def delete_by_doc_id(self, doc_id: str) -> int:
        deleted_count = 0
        if doc_id in self._documents:
            del self._documents[doc_id]
            deleted_count += 1

        affected_entities = set(self._doc_entities.pop(doc_id, set()))
        for entity_id in affected_entities:
            self._entity_to_docs.get(entity_id, set()).discard(doc_id)

        for edge_id, edge in list(self._edges.items()):
            if edge.get("doc_id") == doc_id or (
                edge.get("relation_type") == "MENTIONS" and edge.get("source_id") == doc_id
            ):
                del self._edges[edge_id]
                deleted_count += 1

        for entity_id in affected_entities:
            self._recompute_entity_acl(entity_id)
        deleted_count += self._delete_orphan_entities()
        return deleted_count

    async def get_all_document_ids(self) -> set[str]:
        return set(self._documents)

    async def document_exists(self, doc_id: str) -> bool:
        return doc_id in self._documents

    async def document_graph_exists(self, doc_id: str) -> bool:
        if doc_id in self._documents:
            return True
        return any(
            edge.get("relation_type") == "CO_OCCURS" and edge.get("doc_id") == doc_id
            for edge in self._edges.values()
        )

    async def get_all_entity_ids(self) -> set[str]:
        return set(self._nodes)

    async def delete_orphan_entities(self) -> int:
        return self._delete_orphan_entities()

    def count_nodes(self) -> int:
        return (
            len(self._nodes)
            + len(self._documents)
            + len(self._queries)
            + len(self._answers)
            + len(self._messages)
        )

    def count_edges(self) -> int:
        return len(self._edges) + len(self._query_answer_edges) + len(self._next_edges)

    def get_node(self, entity_id: str) -> dict[str, Any] | None:
        return self._nodes.get(entity_id)

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self._documents.get(doc_id)

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        return self._edges.get(edge_id)

    def get_edges_by_type(self, relation_type: str) -> list[dict[str, Any]]:
        return [
            edge
            for edge in self._edges.values()
            if str(edge.get("relation_type", "")).upper() == relation_type.upper()
        ]

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
        scope = acl_scope or {}
        query_owner = scope.get("owner_user_id") or owner_user_id
        query_shared = scope.get("shared_scope")
        self._queries[query_id] = {
            "query_id": query_id,
            "id": query_id,
            "raw_query": raw_query,
            "rewritten_query": rewritten_query,
            "thread_id": thread_id,
            "owner_user_id": owner_user_id,
            "answer_policy": answer_policy,
            "acl_scope": scope,
            "acl_owner_user_id": query_owner or "",
            "acl_shared_scope": query_shared or "",
            "acl_is_public": not query_owner and not query_shared,
            "entities": query_entities,
        }
        self._answers[answer_id] = {
            "answer_id": answer_id,
            "id": answer_id,
            "query_id": query_id,
            "content": answer,
            "source_kind": source_kind,
            "is_abstention": is_abstention,
            "entities": answer_entities,
            "cites": cites,
            "web_sources": web_sources,
            "acl_scope": scope,
            "ingested_at": ingested_at,
        }
        self._query_answer_edges.append((query_id, answer_id))
        self._edges[self._edge_key(query_id, "ANSWERED_BY", answer_id)] = {
            "relation_type": "ANSWERED_BY",
            "source_id": query_id,
            "target_id": answer_id,
        }
        if previous_query_id:
            self._next_edges.append((previous_query_id, query_id))
            self._edges[self._edge_key(previous_query_id, "NEXT", query_id)] = {
                "relation_type": "NEXT",
                "source_id": previous_query_id,
                "target_id": query_id,
            }
        for entity in query_entities:
            entity_id = entity.get("entity_id") or entity.get("name")
            if entity_id:
                edge_id = self._edge_key(query_id, "ABOUT", entity_id)
                self._edges[edge_id] = {
                    "relation_type": "ABOUT",
                    "source_id": query_id,
                    "target_id": entity_id,
                }
        for entity in answer_entities:
            entity_id = entity.get("entity_id") or entity.get("name")
            if entity_id:
                edge_id = self._edge_key(answer_id, "MENTIONS", entity_id)
                self._edges[edge_id] = {
                    "relation_type": "MENTIONS",
                    "source_id": answer_id,
                    "target_id": entity_id,
                }
        for cite in cites:
            doc_id = cite.get("source_id")
            if doc_id:
                edge_id = self._edge_key(answer_id, "CITES", doc_id)
                self._edges[edge_id] = {
                    "relation_type": "CITES",
                    "source_id": answer_id,
                    "target_id": doc_id,
                }

    async def delete_chat_graph(
        self,
        source_id: str | None = None,
        thread_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> int:
        to_delete: list[str] = []
        for edge_id, edge in self._edges.items():
            edge_source = str(edge.get("source_id", "") or "")
            if thread_id and edge.get("thread_id") != thread_id:
                continue
            if source_id and edge_source != source_id:
                continue
            if edge.get("relation_type") in {"ABOUT", "ANSWERED_BY", "NEXT"}:
                continue
            if (
                edge.get("source_kind") == "chat"
                or edge_source.startswith("chat:")
                or thread_id
                or source_id
            ):
                to_delete.append(edge_id)
        for edge_id in to_delete:
            del self._edges[edge_id]
        for message_id, message in list(self._messages.items()):
            if (thread_id and message.get("thread_id") != thread_id) or (
                source_id and message.get("source_id") != source_id
            ):
                continue
            if owner_user_id and message.get("owner_user_id") != owner_user_id:
                continue
            del self._messages[message_id]
        self._delete_orphan_entities()
        return len(to_delete)

    async def close(self) -> None:
        return None


class FakeEntityVectorIndex:
    """In-memory entity vector index for tests. Payload is minimal like real Qdrant."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}

    async def upsert_entity(
        self,
        *,
        entity_id: str,
        name: str,
        entity_type: str,
        type_group: str,
        owner_user_id: str | None,
    ) -> None:
        self._entities[entity_id] = {
            "entity_id": entity_id,
            "type_group": type_group,
            "owner_user_id": owner_user_id or "",
            # internal-only test aid; real Qdrant payload does not store name
            "_name": name,
            "_entity_type": entity_type,
        }

    async def search_similar(
        self,
        *,
        name: str,
        entity_type: str,
        type_group: str,
        owner_user_id: str | None,
        limit: int = 5,
        threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        out = []
        for rec in self._entities.values():
            if rec.get("type_group") != type_group:
                continue
            if owner_user_id and rec.get("owner_user_id") != owner_user_id:
                continue
            from app.ingestion.entity_resolution import normalize_text_token

            n1 = normalize_text_token(name)
            n2 = normalize_text_token(str(rec.get("_name", "")))
            score = 1.0 if n1 == n2 else (0.92 if n1 in n2 or n2 in n1 else 0.0)
            if score >= threshold:
                out.append(
                    {
                        "entity_id": rec["entity_id"],
                        "type_group": rec["type_group"],
                        "owner_user_id": rec["owner_user_id"],
                        "_score": score,
                        "_name": rec.get("_name", ""),
                        "_entity_type": rec.get("_entity_type", ""),
                    }
                )
        out.sort(key=lambda x: -x["_score"])
        return out[:limit]

    async def delete_entities(self, entity_ids: list[str]) -> None:
        for entity_id in entity_ids:
            self._entities.pop(entity_id, None)

    async def close(self) -> None:
        return None

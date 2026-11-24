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
        self._store[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "vector": vector or [0.0] * 384,
            "payload": payload,
        }

    async def delete_chunk(self, chunk_id: str) -> bool:
        if chunk_id in self._store:
            del self._store[chunk_id]
            return True
        return False

    async def delete_by_doc_id(self, doc_id: str) -> int:
        to_delete = [cid for cid, record in self._store.items() if record.get("doc_id") == doc_id]
        for cid in to_delete:
            del self._store[cid]
        return len(to_delete)

    async def get_all_chunk_ids(self) -> set[str]:
        return set(self._store)

    def count(self) -> int:
        return len(self._store)

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        return self._store.get(chunk_id)

    async def close(self) -> None:
        return None


class FakeNeo4jIndexer:
    """In-memory Neo4j indexer fake for tests."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, dict[str, Any]] = {}
        self._entity_to_chunks: dict[str, set[str]] = {}

    async def merge_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        self._chunks[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "owner_user_id": owner_user_id,
            "acl_scope": acl_scope or {},
            "temporal": temporal or {},
        }

    async def link_chunk_entity(self, chunk_id: str, entity_id: str) -> None:
        self._entity_to_chunks.setdefault(entity_id, set()).add(chunk_id)
        self._recompute_entity_acl(entity_id)

    async def link_chunk_to_entities(self, chunk_id: str, entity_ids: list[str]) -> int:
        for eid in entity_ids:
            await self.link_chunk_entity(chunk_id, eid)
        return len(entity_ids)

    def _recompute_entity_acl(self, entity_id: str) -> None:
        if entity_id not in self._nodes:
            return
        chunk_ids = self._entity_to_chunks.get(entity_id, set())
        chunks = [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]
        if not chunks:
            return
        doc_ids = {c["doc_id"] for c in chunks if c.get("doc_id")}
        is_public = any(c.get("acl_scope", {}).get("is_public", False) for c in chunks)
        roles: set[str] = set()
        groups: set[str] = set()
        for c in chunks:
            roles.update(c.get("acl_scope", {}).get("allowed_roles", []))
            groups.update(c.get("acl_scope", {}).get("allowed_groups", []))
        node = self._nodes[entity_id]
        node["doc_ids"] = list(doc_ids)
        node["acl_scope"] = {
            "tenant_id": "default",
            "is_public": is_public,
            "allowed_roles": list(roles),
            "allowed_groups": list(groups),
        }
        node["acl_is_public"] = is_public
        node["acl_allowed_roles"] = list(roles)
        node["acl_allowed_groups"] = list(groups)

    async def delete_chunk(self, chunk_id: str) -> bool:
        if chunk_id in self._chunks:
            del self._chunks[chunk_id]
            for entity_id in list(self._entity_to_chunks.keys()):
                self._entity_to_chunks[entity_id].discard(chunk_id)
                self._recompute_entity_acl(entity_id)
            return True
        return False

    async def merge_node(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        scope = acl_scope or {}
        props = properties or {}
        doc_id = props.get("doc_id", "")
        if entity_id in self._nodes:
            existing = self._nodes[entity_id]
            existing["name"] = name
            existing["entity_type"] = entity_type
            if doc_id:
                existing.setdefault("doc_ids", []).append(doc_id)
            ex_scope = existing.get("acl_scope", {})
            is_public = ex_scope.get("is_public", False) or scope.get("is_public", False)
            roles = set(ex_scope.get("allowed_roles", [])) | set(scope.get("allowed_roles", []))
            groups = set(ex_scope.get("allowed_groups", [])) | set(scope.get("allowed_groups", []))
            merged_scope = {
                "tenant_id": scope.get("tenant_id", "default"),
                "is_public": is_public,
                "allowed_roles": list(roles),
                "allowed_groups": list(groups),
            }
            existing["acl_scope"] = merged_scope
            existing["acl_is_public"] = is_public
            existing["acl_allowed_roles"] = list(roles)
            existing["acl_allowed_groups"] = list(groups)
        else:
            is_public = bool(scope.get("is_public", False))
            init_roles = list(scope.get("allowed_roles", []))
            init_groups = list(scope.get("allowed_groups", []))
            self._nodes[entity_id] = {
                "entity_id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "acl_scope": dict(scope),
                "acl_is_public": is_public,
                "acl_allowed_roles": init_roles,
                "acl_allowed_groups": init_groups,
                "doc_ids": [doc_id] if doc_id else [],
                "temporal": temporal or {},
                "properties": props,
            }

    async def merge_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        props = properties or {}
        chunk_id = props.get("chunk_id") or props.get("doc_id") or ""
        edge_id = f"{source_id}-[{relation_type}:{chunk_id}]->{target_id}"
        self._edges[edge_id] = {
            "edge_id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "acl_scope": acl_scope or {},
            "temporal": temporal or {},
            "properties": props,
            "chunk_id": chunk_id,
            "doc_id": props.get("doc_id", ""),
        }
        return edge_id

    async def delete_by_doc_id(self, doc_id: str) -> int:
        deleted_count = 0
        chunks_to_del = [cid for cid, data in self._chunks.items() if data.get("doc_id") == doc_id]
        for cid in chunks_to_del:
            del self._chunks[cid]
            deleted_count += 1

        edges_to_del = [
            eid
            for eid, data in self._edges.items()
            if data.get("doc_id") == doc_id or data.get("properties", {}).get("doc_id") == doc_id
        ]
        for eid in edges_to_del:
            del self._edges[eid]
            deleted_count += 1

        for entity_id in list(self._entity_to_chunks.keys()):
            for cid in chunks_to_del:
                self._entity_to_chunks[entity_id].discard(cid)
            remaining_chunks = [
                cid for cid in self._entity_to_chunks[entity_id] if cid in self._chunks
            ]
            if not remaining_chunks:
                if entity_id in self._nodes:
                    del self._nodes[entity_id]
                    deleted_count += 1
            else:
                self._recompute_entity_acl(entity_id)

        nodes_to_del = [
            nid
            for nid, data in self._nodes.items()
            if data.get("properties", {}).get("doc_id") == doc_id
            and nid not in self._entity_to_chunks
        ]
        for nid in nodes_to_del:
            del self._nodes[nid]
            deleted_count += 1
        return deleted_count

    async def get_all_chunk_ids(self) -> set[str]:
        return set(self._chunks)

    def get_chunk_ids(self) -> set[str]:
        return set(self._chunks)

    def count_nodes(self) -> int:
        return len(self._nodes)

    def count_edges(self) -> int:
        return len(self._edges)

    def get_node(self, entity_id: str) -> dict[str, Any] | None:
        return self._nodes.get(entity_id)

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        return self._edges.get(edge_id)

    async def delete_chat_graph(
        self,
        source_id: str | None = None,
        thread_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> int:
        to_delete = []
        for edge_id, edge in self._edges.items():
            props = edge.get("properties", {})
            if thread_id and props.get("thread_id") != thread_id:
                continue
            if source_id and props.get("source_id") != source_id:
                continue
            if owner_user_id and props.get("owner_user_id") != owner_user_id:
                continue
            if (
                props.get("source_kind") == "chat"
                or str(props.get("source_id", "")).startswith("chat:")
                or thread_id
                or source_id
            ):
                to_delete.append(edge_id)
        for edge_id in to_delete:
            del self._edges[edge_id]
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
        for eid in entity_ids:
            self._entities.pop(eid, None)

    async def close(self) -> None:
        return None

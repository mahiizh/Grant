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

    async def merge_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        acl_scope: dict[str, Any] | None = None,
        temporal: dict[str, Any] | None = None,
    ) -> None:
        self._chunks[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "acl_scope": acl_scope or {},
            "temporal": temporal or {},
        }

    async def link_chunk_to_entities(self, chunk_id: str, entity_ids: list[str]) -> int:
        return len(entity_ids)

    async def delete_chunk(self, chunk_id: str) -> bool:
        if chunk_id in self._chunks:
            del self._chunks[chunk_id]
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
        self._nodes[entity_id] = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": entity_type,
            "acl_scope": acl_scope or {},
            "temporal": temporal or {},
            "properties": properties or {},
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
        edge_id = f"{source_id}-[{relation_type}]->{target_id}"
        self._edges[edge_id] = {
            "edge_id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "acl_scope": acl_scope or {},
            "temporal": temporal or {},
            "properties": properties or {},
        }
        return edge_id

    async def delete_by_doc_id(self, doc_id: str) -> int:
        deleted_count = 0
        chunks_to_del = [cid for cid, data in self._chunks.items() if data.get("doc_id") == doc_id]
        for cid in chunks_to_del:
            del self._chunks[cid]
            deleted_count += 1
        nodes_to_del = [
            nid
            for nid, data in self._nodes.items()
            if data.get("properties", {}).get("doc_id") == doc_id
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

    async def close(self) -> None:
        return None

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores
from app.retrieval.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


def chunk_id_to_point_id(chunk_id: str) -> str:
    """Generate a deterministic UUID from chunk_id for Qdrant point addressing."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


class QdrantIndexer:
    """Production Qdrant indexer managing hybrid dense (384-dim) and BM25 sparse vectors."""

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
        assert_writable_stores(settings)
        self.collection_name = settings.QDRANT_COLLECTION
        self.client = client or AsyncQdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
            check_compatibility=False,
        )
        self.embedding_service = get_embedding_service()

    async def upsert_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        text: str,
        payload: dict[str, Any] | None = None,
        vector: list[float] | None = None,
    ) -> None:
        """Embed and upsert chunk with dense and sparse vectors and payload."""
        data_payload = dict(payload or {})
        data_payload.setdefault("chunk_id", chunk_id)
        data_payload.setdefault("doc_id", doc_id)
        data_payload.setdefault("text", text)

        # Compute embeddings if vector not explicitly provided
        if vector is not None:
            dense_vec = vector
            sparse_vec = await self.embedding_service.aembed_query_sparse(text)
        else:
            dense_vec, sparse_vec = await self.embedding_service.aembed_query(text)

        pt_id = chunk_id_to_point_id(chunk_id)

        point = models.PointStruct(
            id=pt_id,
            vector={
                "dense": dense_vec,
                "sparse": models.SparseVector(
                    indices=sparse_vec.indices,
                    values=sparse_vec.values,
                ),
            },
            payload=data_payload,
        )

        await self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

    async def delete_chunk(self, chunk_id: str) -> bool:
        """Remove a specific chunk by ID."""
        pt_id = chunk_id_to_point_id(chunk_id)
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[pt_id]),
        )
        return True

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Remove all chunks belonging to a document."""
        flt = models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchValue(value=doc_id),
                )
            ]
        )
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=flt),
        )
        return 1

    async def count(self) -> int:
        """Return total indexed chunks in collection."""
        try:
            info = await self.client.get_collection(self.collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    async def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Retrieve chunk payload by chunk_id."""
        pt_id = chunk_id_to_point_id(chunk_id)
        pts = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=[pt_id],
            with_payload=True,
        )
        if pts:
            return pts[0].payload
        return None

    async def get_all_chunk_ids(self) -> set[str]:
        """Scroll all points to retrieve all chunk_ids present in Qdrant."""
        chunk_ids: set[str] = set()
        offset = None
        while True:
            records, next_offset = await self.client.scroll(
                collection_name=self.collection_name,
                limit=1000,
                offset=offset,
                with_payload=["chunk_id"],
                with_vectors=False,
            )
            for rec in records:
                cid = (rec.payload or {}).get("chunk_id")
                if cid:
                    chunk_ids.add(str(cid))
            if next_offset is None or not records:
                break
            offset = next_offset
        return chunk_ids

    async def close(self) -> None:
        """Close Qdrant client connection."""
        await self.client.close()


def entity_id_to_point_id(entity_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"entity:{entity_id}"))


class EntityVectorIndex:
    """Qdrant collection storing entity embeddings for SBERT-based resolution.

    Payload is intentionally minimal: vector + entity_id + type_group + owner_user_id.
    Entity-doc/source links live in Postgres entity_mentions and are synced via outbox.
    """

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
        self.collection_name = settings.QDRANT_ENTITY_COLLECTION
        self.client = client or AsyncQdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
            check_compatibility=False,
        )
        self.embedding_service = get_embedding_service()

    async def upsert_entity(
        self,
        *,
        entity_id: str,
        name: str,
        entity_type: str,
        type_group: str,
        owner_user_id: str | None,
    ) -> None:
        text = f"{name} [{entity_type}]"
        dense = await self.embedding_service.aembed_query_dense(text)
        payload = {
            "entity_id": entity_id,
            "type_group": type_group,
            "owner_user_id": owner_user_id or "",
        }
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=entity_id_to_point_id(entity_id),
                    vector=dense,
                    payload=payload,
                )
            ],
        )

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
        query_vec = await self.embedding_service.aembed_query_dense(
            f"{name} [{entity_type}]"
        )
        must: list[models.Condition] = [
            models.FieldCondition(key="type_group", match=models.MatchValue(value=type_group))
        ]
        if owner_user_id:
            must.append(
                models.FieldCondition(key="owner_user_id", match=models.MatchValue(value=owner_user_id))
            )
        flt = models.Filter(must=must)
        res = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vec,
            query_filter=flt,
            limit=limit,
            with_payload=True,
        )
        points = res.points
        out: list[dict[str, Any]] = []
        for p in points:
            score = float(getattr(p, "score", 0.0) or 0.0)
            if score < threshold:
                continue
            payload = dict(getattr(p, "payload", None) or {})
            payload["_score"] = score
            out.append(payload)
        return out

    async def delete_by_owner(self, owner_user_id: str) -> None:
        flt = models.Filter(
            must=[models.FieldCondition(key="owner_user_id", match=models.MatchValue(value=owner_user_id))]
        )
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=flt),
        )

    async def delete_entities(self, entity_ids: list[str]) -> None:
        if not entity_ids:
            return
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(
                points=[entity_id_to_point_id(eid) for eid in entity_ids]
            ),
        )

    async def close(self) -> None:
        await self.client.close()

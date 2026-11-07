import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.retrieval.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


def chunk_id_to_point_id(chunk_id: str) -> str:
    """Generate a deterministic UUID from chunk_id for Qdrant point addressing."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


class QdrantIndexer:
    """Production Qdrant indexer managing hybrid dense (384-dim) and BM25 sparse vectors."""

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
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
            sparse_vec = self.embedding_service.embed_query_sparse(text)
        else:
            dense_vec, sparse_vec = self.embedding_service.embed_query(text)

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

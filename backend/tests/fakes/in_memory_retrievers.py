import hashlib
import math
import re
from collections import Counter, deque
from collections.abc import Sequence
from typing import Any

from app.domain import Chunk, Entity, Evidence, Relation
from app.domain.ids import normalize_entity_name
from app.retrieval.filters import RetrievalFilter


class AwaitableList(list):
    """A list that can be awaited as well as accessed directly synchronously."""

    def __await__(self) -> Any:
        async def _coro() -> list:
            return self

        return _coro().__await__()


def text_to_embedding(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        return vec
    for word in words:
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) % 2 == 0) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    return max(0.0, min(1.0, dot))


class FakeDenseRetriever:
    """In-memory MD5-based fake dense retriever for unit tests."""

    def __init__(self, embedding_dim: int = 128) -> None:
        self.dim = embedding_dim
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, list[float]] = {}

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = {c.chunk_id: c for c in chunks}
        self._vectors = {c.chunk_id: text_to_embedding(c.text, dim=self.dim) for c in chunks}

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[tuple[str, float]]:
        if not self._chunks:
            return []
        query_vec = text_to_embedding(query, dim=self.dim)
        scores: dict[str, float] = {}
        for chunk_id, chunk in self._chunks.items():
            if filter_criteria is not None and not filter_criteria.permits_chunk(chunk):
                continue
            sim = cosine_similarity(query_vec, self._vectors[chunk_id])
            if sim > 0.0:
                scores[chunk_id] = sim
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]


class FakeBM25Retriever:
    """In-memory Python BM25 retriever for unit tests."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: dict[str, Chunk] = {}
        self._doc_tokens: dict[str, list[str]] = {}
        self._doc_freqs: dict[str, int] = Counter()
        self._avg_dl: float = 0.0

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        self._chunks.clear()
        self._doc_tokens.clear()
        self._doc_freqs.clear()
        total_len = 0
        for chunk in chunks:
            tokens = [t for t in re.sub(r"[^\w\s-]", " ", chunk.text.lower()).split() if len(t) > 1]
            self._chunks[chunk.chunk_id] = chunk
            self._doc_tokens[chunk.chunk_id] = tokens
            total_len += len(tokens)
            for t in set(tokens):
                self._doc_freqs[t] += 1
        self._avg_dl = (total_len / len(chunks)) if chunks else 1.0

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[tuple[str, float]]:
        query_tokens = [t for t in re.sub(r"[^\w\s-]", " ", query.lower()).split() if len(t) > 1]
        if not query_tokens or not self._chunks:
            return []
        scores: dict[str, float] = {}
        doc_count = len(self._chunks)
        candidates = [
            cid
            for cid, chunk in self._chunks.items()
            if filter_criteria is None or filter_criteria.permits_chunk(chunk)
        ]
        for token in query_tokens:
            n_q = self._doc_freqs.get(token, 0)
            if n_q == 0:
                continue
            idf = math.log(1.0 + (doc_count - n_q + 0.5) / (n_q + 0.5))
            for cid in candidates:
                tokens = self._doc_tokens[cid]
                tf = tokens.count(token)
                if tf == 0:
                    continue
                doc_len = len(tokens)
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self._avg_dl))
                scores[cid] = scores.get(cid, 0.0) + (idf * (numerator / denominator))
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]


class FakeReranker:
    """Deterministic reranker fake that records the candidates it was given."""

    def __init__(self) -> None:
        self.seen_chunk_ids: list[str] = []

    def rerank_evidence(
        self,
        query: str,
        candidates: Sequence[Evidence],
        top_k: int | None = None,
    ) -> list[Evidence]:
        self.seen_chunk_ids = [c.chunk_id for c in candidates]
        query_lower = query.lower()
        ranked = sorted(
            candidates,
            key=lambda c: c.text.lower().count(query_lower),
            reverse=True,
        )
        return ranked[:top_k] if top_k is not None else ranked


class FakeHybridRetriever:
    """In-memory hybrid retriever combining dense and BM25 using RRF for tests."""

    def __init__(
        self,
        dense: FakeDenseRetriever | None = None,
        sparse: FakeBM25Retriever | None = None,
        reranker: FakeReranker | None = None,
        prefetch_multiplier: int = 5,
    ) -> None:
        self.dense = dense or FakeDenseRetriever()
        self.sparse = sparse or FakeBM25Retriever()
        self.reranker = reranker
        self.prefetch_multiplier = prefetch_multiplier
        self._chunks: dict[str, Chunk] = {}

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = {c.chunk_id: c for c in chunks}
        self.dense.index_chunks(chunks)
        self.sparse.index_chunks(chunks)

    def _evidence_from_scores(
        self,
        results: Sequence[tuple[str, float]],
        method: str,
        filter_criteria: RetrievalFilter | None,
        top_k: int,
    ) -> AwaitableList:
        evidence = AwaitableList()
        for chunk_id, score in results[:top_k]:
            chunk = self._chunks.get(chunk_id)
            if chunk is None:
                continue
            if filter_criteria is not None and not filter_criteria.permits_chunk(chunk):
                continue
            evidence.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    text=chunk.text,
                    score=score,
                    retrieval_method=method,
                    provenance=chunk.provenance,
                )
            )
        return evidence

    def search_dense(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> AwaitableList:
        results = self.dense.search(query, top_k=top_k, filter_criteria=filter_criteria)
        return self._evidence_from_scores(results, "dense", filter_criteria, top_k)

    def search_sparse(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> AwaitableList:
        results = self.sparse.search(query, top_k=top_k, filter_criteria=filter_criteria)
        return self._evidence_from_scores(results, "sparse", filter_criteria, top_k)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
        k: int = 60,
        rerank: bool = False,
        extra_candidates: Sequence[Evidence] | None = None,
        prefetch_k: int | None = None,
        weights: Sequence[float] | None = None,
    ) -> AwaitableList:
        prefetch_limit = prefetch_k if prefetch_k is not None else top_k * self.prefetch_multiplier
        dense_results = self.dense.search(
            query, top_k=prefetch_limit, filter_criteria=filter_criteria
        )
        sparse_results = self.sparse.search(
            query, top_k=prefetch_limit, filter_criteria=filter_criteria
        )
        rrf_scores: dict[str, float] = {}
        w_dense = weights[0] if weights and len(weights) > 0 else 1.0
        w_sparse = weights[1] if weights and len(weights) > 1 else 1.0
        for rank, (chunk_id, _) in enumerate(dense_results):
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + w_dense / (k + rank + 1)
        for rank, (chunk_id, _) in enumerate(sparse_results):
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + w_sparse / (k + rank + 1)
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        # Defense-in-depth: mirror the production payload check even if a fake
        # retriever upstream forgot to apply the ACL predicate.
        if filter_criteria is not None:
            ranked = [
                (chunk_id, score)
                for chunk_id, score in ranked
                if filter_criteria.permits_chunk(self._chunks[chunk_id])
            ]
        ranked = ranked[:top_k]
        # RRF only decides order. Mirror production by carrying the chunk's
        # dense cosine as the evidence score so the relevance gate is realistic.
        dense_scores = dict(dense_results)
        evidence_list = AwaitableList()
        for chunk_id, _rrf_score in ranked:
            chunk = self._chunks[chunk_id]
            evidence_list.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    text=chunk.text,
                    score=dense_scores.get(chunk_id, 0.0),
                    retrieval_method="hybrid",
                    provenance=chunk.provenance,
                )
            )
        if rerank and self.reranker is not None and evidence_list:
            if extra_candidates:
                seen = {item.chunk_id for item in evidence_list}
                for item in extra_candidates:
                    if item.chunk_id not in seen:
                        evidence_list.append(item)
                        seen.add(item.chunk_id)
            return AwaitableList(
                self.reranker.rerank_evidence(query=query, candidates=evidence_list, top_k=top_k)
            )
        return evidence_list


class FakeGraphRetriever:
    """In-memory BFS graph retriever for tests."""

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._name_to_id: dict[str, str] = {}
        self._adjacency: dict[str, list[tuple[str, str, Relation]]] = {}
        self._chunks: dict[str, Chunk] = {}

    def index_graph(
        self,
        entities: Sequence[Entity],
        relations: Sequence[Relation],
        chunks: Sequence[Chunk] | None = None,
    ) -> None:
        self._entities.clear()
        self._name_to_id.clear()
        for e in entities:
            norm_name = normalize_entity_name(e.name)
            if e.entity_id in self._entities:
                existing = self._entities[e.entity_id]
                merged = existing.model_copy(
                    update={
                        "acl_scope": existing.acl_scope.union(e.acl_scope),
                        "source_chunk_ids": list(
                            dict.fromkeys(existing.source_chunk_ids + e.source_chunk_ids)
                        ),
                    }
                )
                self._entities[e.entity_id] = merged
            else:
                self._entities[e.entity_id] = e
                self._name_to_id[norm_name] = e.entity_id

        self._adjacency.clear()
        for r in relations:
            self._adjacency.setdefault(r.source_entity_id, []).append(
                (r.relation_type, r.target_entity_id, r)
            )
        if chunks:
            self._chunks = {c.chunk_id: c for c in chunks}
            for e_id, e in list(self._entities.items()):
                linked_chunks = [
                    self._chunks[cid] for cid in e.source_chunk_ids if cid in self._chunks
                ]
                if linked_chunks:
                    new_scope = e.acl_scope
                    for chk in linked_chunks:
                        new_scope = new_scope.union(chk.acl_scope)
                    if new_scope != e.acl_scope:
                        self._entities[e_id] = e.model_copy(update={"acl_scope": new_scope})

    def _permits_source_chunk(self, chunk_id: str, filter_criteria: RetrievalFilter) -> bool:
        chunk = self._chunks.get(chunk_id)
        return chunk is not None and filter_criteria.permits_chunk(chunk)

    def _permits_entity(self, entity: Entity, filter_criteria: RetrievalFilter | None) -> bool:
        if filter_criteria is None:
            return True
        linked = [
            cid for cid in entity.source_chunk_ids if cid in self._chunks
        ]
        if linked:
            if not any(self._permits_source_chunk(cid, filter_criteria) for cid in linked):
                return False
        elif not entity.acl_scope.permits(
            owner_user_id=filter_criteria.owner_user_id,
            shared_scope=filter_criteria.acl_scope.shared_scope,
            is_admin=filter_criteria.is_admin,
        ):
            return False
        return True

    def _permits_relation(self, relation: Relation, filter_criteria: RetrievalFilter | None) -> bool:
        if filter_criteria is None:
            return True
        linked = [
            cid for cid in relation.source_chunk_ids if cid in self._chunks
        ]
        if linked:
            if not any(self._permits_source_chunk(cid, filter_criteria) for cid in linked):
                return False
        elif not relation.acl_scope.permits(
            owner_user_id=filter_criteria.owner_user_id,
            shared_scope=filter_criteria.acl_scope.shared_scope,
            is_admin=filter_criteria.is_admin,
        ):
            return False
        return True

    def search_entities(
        self,
        query: str,
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> AwaitableList:
        q_lower = query.lower()
        matches = [
            {"name": e.name, "entity_type": e.entity_type}
            for e in self._entities.values()
            if e.name.lower() in q_lower and self._permits_entity(e, filter_criteria)
        ]
        return AwaitableList(matches[:top_k])

    def find_path(
        self,
        start_entity_name: str,
        end_entity_name: str,
        max_depth: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> Any:
        src_id = self._name_to_id.get(normalize_entity_name(start_entity_name))
        tgt_id = self._name_to_id.get(normalize_entity_name(end_entity_name))
        if not src_id or not tgt_id:
            return None
        if not self._permits_entity(self._entities[src_id], filter_criteria) or not (
            self._permits_entity(self._entities[tgt_id], filter_criteria)
        ):
            return None
        queue: deque[tuple[str, list[str]]] = deque([(src_id, [self._entities[src_id].name])])
        visited = {src_id}
        while queue:
            curr_id, path = queue.popleft()
            if curr_id == tgt_id:
                return AwaitableList(path)
            if len(path) // 2 >= max_depth:
                continue
            for rel_type, next_id, rel in self._adjacency.get(curr_id, []):
                if (
                    next_id not in visited
                    and self._permits_relation(rel, filter_criteria)
                    and self._permits_entity(self._entities[next_id], filter_criteria)
                ):
                    visited.add(next_id)
                    queue.append((next_id, path + [rel_type, self._entities[next_id].name]))
        return None

    def retrieve_path_evidence(
        self,
        path: list[str] | None,
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> AwaitableList:
        evidence = AwaitableList()
        if not path:
            return evidence
        seen_chunks: set[str] = set()
        for i in range(0, len(path), 2):
            ent_name = path[i]
            ent_id = self._name_to_id.get(normalize_entity_name(ent_name))
            if not ent_id:
                continue
            entity = self._entities[ent_id]
            for chunk_id in entity.source_chunk_ids:
                if chunk_id in seen_chunks:
                    continue
                chunk = self._chunks.get(chunk_id)
                if chunk and (filter_criteria is None or filter_criteria.permits_chunk(chunk)):
                    seen_chunks.add(chunk_id)
                    evidence.append(
                        Evidence(
                            chunk_id=chunk.chunk_id,
                            doc_id=chunk.doc_id,
                            text=chunk.text,
                            score=1.0,
                            retrieval_method="graph",
                            provenance=chunk.provenance,
                            path=path,
                        )
                    )
                    if len(evidence) >= top_k:
                        return evidence
        return evidence

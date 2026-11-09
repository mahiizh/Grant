import logging
import re
from functools import lru_cache

from app.domain.ids import normalize_entity_name
from app.llm.gateway import ModelGateway
from app.retrieval.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


def normalize_text_token(name: str) -> str:
    """Normalize entity text by lowercasing, stripping punctuation and common version suffixes."""
    norm = normalize_entity_name(name)
    # Strip common version patterns like "16", "v2", "v2.4.1"
    norm = re.sub(r"\b(v?\d+(\.\d+)*)\b", "", norm).strip()
    norm = re.sub(r"\s+", " ", norm)
    # Common technology aliases
    alias_map = {
        "postgres": "postgresql",
        "pg": "postgresql",
        "redis-server": "redis",
        "k8s": "kubernetes",
        "payment-gw": "paymentgateway",
        "payment-gateway": "paymentgateway",
    }
    return alias_map.get(norm, norm)


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    return max(0.0, min(1.0, dot))


class EntityResolver:
    """Resolves entity aliases via blocking, dense embedding similarity, and LLM adjudication."""

    def __init__(
        self,
        sim_high_threshold: float = 0.90,
        sim_low_threshold: float = 0.75,
        gateway: ModelGateway | None = None,
    ) -> None:
        self.sim_high = sim_high_threshold
        self.sim_low = sim_low_threshold
        self.gateway = gateway or ModelGateway()
        self.embedding_service = get_embedding_service()
        self._cache: dict[tuple[str, str], bool] = {}

    def is_same_entity_rule(
        self, name_a: str, type_a: str, name_b: str, type_b: str
    ) -> bool | None:
        """Deterministic rule-based check."""
        # Types must match (or one is generic)
        if (
            type_a.lower() != type_b.lower()
            and type_a.lower() not in ("entity", "unknown")
            and type_b.lower() not in ("entity", "unknown")
        ):
            return False

        norm_a = normalize_text_token(name_a)
        norm_b = normalize_text_token(name_b)

        if norm_a == norm_b:
            return True

        if norm_a in norm_b or norm_b in norm_a:
            # e.g., postgresql in postgresql 16
            return True

        return None

    async def are_same_entity(
        self,
        name_a: str,
        type_a: str,
        name_b: str,
        type_b: str,
    ) -> bool:
        """Adjudicate whether two entity references refer to the same real-world entity."""
        pair_key = (f"{name_a}:{type_a}".lower(), f"{name_b}:{type_b}".lower())
        if pair_key in self._cache:
            return self._cache[pair_key]

        # 1. Rule / Blocking step
        rule_result = self.is_same_entity_rule(name_a, type_a, name_b, type_b)
        if rule_result is not None:
            self._cache[pair_key] = rule_result
            return rule_result

        # 2. Embedding similarity step
        vec_a = self.embedding_service.embed_query_dense(name_a)
        vec_b = self.embedding_service.embed_query_dense(name_b)
        sim = cosine_sim(vec_a, vec_b)

        if sim >= self.sim_high:
            self._cache[pair_key] = True
            return True

        if sim < self.sim_low:
            self._cache[pair_key] = False
            return False

        # 3. LLM Adjudication for borderline cases (between 0.75 and 0.90)
        prompt = (
            f"You are an entity resolution expert. Determine if these two entity mentions refer to the same entity:\n"
            f"Entity A: '{name_a}' (Type: {type_a})\n"
            f"Entity B: '{name_b}' (Type: {type_b})\n"
            f"Answer ONLY 'YES' or 'NO'."
        )
        try:
            resp = await self.gateway.complete(prompt=prompt, max_tokens=10, temperature=0.0)
            is_match = "yes" in resp.content.strip().lower()
            self._cache[pair_key] = is_match
            return is_match
        except Exception:
            # Fallback to embedding score decision
            is_match = sim >= 0.83
            self._cache[pair_key] = is_match
            return is_match


@lru_cache(maxsize=1)
def get_entity_resolver() -> EntityResolver:
    return EntityResolver()

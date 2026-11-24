import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.domain.ids import normalize_entity_name
from app.retrieval.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

# Coarse type groups for resolution. Entities can merge only within same group.
TYPE_GROUPS: dict[str, str] = {
    "Person": "person",
    "Organization": "org",
    "Team": "org",
    "Software": "technology",
    "Database": "technology",
    "System": "technology",
    "Technology": "technology",
    "Service": "technology",
    "Standard": "standard",
    "Regulation": "standard",
    "Control": "control",
    "Process": "process",
    "Concept": "concept",
    "Document": "document",
    "Location": "location",
    "Incident": "incident",
    "Role": "role",
    "Metric": "metric",
    "Product": "technology",
}

VERSION_RE = re.compile(
    r"\b(?:v\d+(?:\.\d+)*|\d{4}(?:-\d{2})?|\d+(?:\.\d+)+)\b",
    re.IGNORECASE,
)


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def normalize_text_token(name: str) -> str:
    """Normalize entity text for comparison, removing punctuation and normalizing whitespace."""
    norm = normalize_entity_name(name).replace("_", " ").strip()
    norm = re.sub(r"\s+", " ", norm)
    alias_map = {
        "postgres": "postgresql",
        "pg": "postgresql",
        "k8s": "kubernetes",
        "payment gw": "paymentgateway",
        "payment gateway": "paymentgateway",
        "payment-gw": "paymentgateway",
        "payment-gateway": "paymentgateway",
    }
    return alias_map.get(norm, norm)


def type_group(entity_type: str) -> str:
    return TYPE_GROUPS.get(entity_type, entity_type.strip().lower() or "unknown")


def extract_version_tokens(name: str) -> tuple[str, tuple[str, ...]]:
    """Return (base_name_without_versions, version_tokens)."""
    versions = tuple(sorted(m.group(0).lower() for m in VERSION_RE.finditer(name)))
    base = VERSION_RE.sub(" ", name)
    base = re.sub(r"[^\w\s-]", " ", base.lower())
    base = re.sub(r"\s+", " ", base).strip()
    return base, versions


def names_differ_in_version_or_number(name_a: str, name_b: str) -> bool:
    base_a, ver_a = extract_version_tokens(name_a)
    base_b, ver_b = extract_version_tokens(name_b)
    if not base_a or not base_b:
        return False

    norm_a = normalize_text_token(base_a)
    norm_b = normalize_text_token(base_b)

    # same base after stripping version tokens, different version tokens -> variant
    if norm_a == norm_b and ver_a != ver_b:
        return True

    # fallback: compare numeric-token-stripped bases; if equal but numeric tokens differ,
    # treat as version/number variant (e.g. PostgreSQL vs PostgreSQL 16)
    nums_a = tuple(sorted(re.findall(r"\d+", name_a)))
    nums_b = tuple(sorted(re.findall(r"\d+", name_b)))
    base_a_no_nums = normalize_text_token(re.sub(r"\d+", " ", base_a))
    base_b_no_nums = normalize_text_token(re.sub(r"\d+", " ", base_b))
    return bool(base_a_no_nums and base_a_no_nums == base_b_no_nums and nums_a != nums_b)


def base_entity_name(name: str) -> str:
    base, _ = extract_version_tokens(name)
    base = re.sub(r"\s+", " ", base).strip(" -_:")
    return base or name.strip()


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


@dataclass
class ResolvedEntity:
    entity_id: str
    canonical_id: str
    name: str
    entity_type: str
    type_group: str
    score: float = 1.0
    merged_from: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    is_new: bool = True


class EntityResolver:
    """SBERT-based entity resolver. No LLM in ingestion path.

    Compatibility: keeps async `are_same_entity` used by existing tests.
    """

    def __init__(
        self,
        sim_high_threshold: float | None = None,
        sim_low_threshold: float = 0.75,
        gateway: Any = None,  # ignored, kept for compatibility
    ) -> None:
        settings = get_settings()
        self.sim_high = sim_high_threshold if sim_high_threshold is not None else settings.ENTITY_RESOLUTION_THRESHOLD
        self.sim_low = sim_low_threshold
        self.embedding_service = get_embedding_service()
        self._cache: dict[tuple[str, str], bool] = {}

    def is_same_entity_rule(self, name_a: str, type_a: str, name_b: str, type_b: str) -> bool | None:
        if type_group(type_a) != type_group(type_b):
            return False
        if names_differ_in_version_or_number(name_a, name_b):
            return False
        norm_a = normalize_text_token(name_a)
        norm_b = normalize_text_token(name_b)
        if norm_a == norm_b:
            return True
        # conservative containment only for short aliases, not for versioned names
        if norm_a in norm_b or norm_b in norm_a:
            # avoid merging when numeric tokens differ
            nums_a = set(re.findall(r"\d+", name_a))
            nums_b = set(re.findall(r"\d+", name_b))
            return nums_a == nums_b
        return None

    async def are_same_entity(self, name_a: str, type_a: str, name_b: str, type_b: str) -> bool:
        pair_key = (f"{name_a}:{type_a}".lower(), f"{name_b}:{type_b}".lower())
        if pair_key in self._cache:
            return self._cache[pair_key]

        rule_result = self.is_same_entity_rule(name_a, type_a, name_b, type_b)
        if rule_result is not None:
            self._cache[pair_key] = rule_result
            return rule_result

        vec_a = self.embedding_service.embed_query_dense(f"{name_a} [{type_a}]")
        vec_b = self.embedding_service.embed_query_dense(f"{name_b} [{type_b}]")
        sim = cosine_sim(vec_a, vec_b)
        result = sim >= self.sim_high
        self._cache[pair_key] = result
        return result


VERSION_OF_TYPES = {"Software", "Standard", "Document"}


@dataclass
class ResolvedMention:
    original_name: str
    original_type: str
    entity_id: str
    canonical_id: str
    name: str
    entity_type: str
    type_group: str
    aliases: list[str] = field(default_factory=list)
    is_new: bool = True
    score: float = 1.0


class IngestionEntityResolver:
    """Resolve extracted mentions against owner-scoped Qdrant entity vectors.

    Qdrant payload is minimal (entity_id/type_group/owner_user_id). Canonical entity
    metadata lives in-memory/DB entity registry; entity<->source links live in Postgres
    entity_mentions and sync to Neo4j via outbox.
    """

    def __init__(
        self,
        entity_index: Any = None,
        threshold: float | None = None,
        session: Any = None,
    ) -> None:
        settings = get_settings()
        self.threshold = threshold if threshold is not None else settings.ENTITY_RESOLUTION_THRESHOLD
        self.top_k = settings.ENTITY_RESOLUTION_TOP_K
        self._entity_index = entity_index
        self._session = session
        self._local_cache: dict[tuple[str, str, str], ResolvedMention] = {}
        self._registry: dict[str, dict[str, Any]] = {}

    @property
    def entity_index(self) -> Any:
        if self._entity_index is None:
            from app.indexing.qdrant_indexer import EntityVectorIndex

            self._entity_index = EntityVectorIndex()
        return self._entity_index

    async def _lookup_entity(self, entity_id: str) -> dict[str, Any] | None:
        if entity_id in self._registry:
            return self._registry[entity_id]
        if self._session is None:
            return None
        try:
            from sqlalchemy import select

            from app.db.models import EntityRecord

            row = (
                await self._session.execute(
                    select(EntityRecord).where(EntityRecord.entity_id == entity_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            rec = {
                "entity_id": row.entity_id,
                "name": row.canonical_name,
                "entity_type": row.entity_type,
                "type_group": row.type_group,
                "aliases": list(row.aliases or []),
                "owner_user_id": row.owner_user_id,
            }
            self._registry[entity_id] = rec
            return rec
        except Exception:
            logger.debug("Entity registry lookup failed for %s", entity_id, exc_info=True)
            return None

    async def _upsert_entity_record(self, resolved: ResolvedMention, owner_user_id: str | None) -> None:
        self._registry[resolved.entity_id] = {
            "entity_id": resolved.entity_id,
            "name": resolved.name,
            "entity_type": resolved.entity_type,
            "type_group": resolved.type_group,
            "aliases": list(resolved.aliases),
            "owner_user_id": owner_user_id,
        }
        if self._session is None:
            return
        try:
            from sqlalchemy import select

            from app.db.models import EntityRecord

            existing = (
                await self._session.execute(
                    select(EntityRecord).where(EntityRecord.entity_id == resolved.entity_id)
                )
            ).scalar_one_or_none()
            if existing is None:
                self._session.add(
                    EntityRecord(
                        entity_id=resolved.entity_id,
                        canonical_name=resolved.name,
                        entity_type=resolved.entity_type,
                        type_group=resolved.type_group,
                        owner_user_id=owner_user_id,
                        aliases=list(resolved.aliases),
                    )
                )
            else:
                existing.canonical_name = resolved.name
                existing.entity_type = resolved.entity_type
                existing.type_group = resolved.type_group
                existing.aliases = list(dict.fromkeys([*(existing.aliases or []), *resolved.aliases]))
        except Exception:
            logger.debug("Failed to upsert EntityRecord for %s", resolved.entity_id, exc_info=True)

    async def _record_mention(
        self,
        *,
        entity_id: str,
        entity_type: str,
        owner_user_id: str | None,
        source_id: str | None,
        doc_id: str | None,
        surface_form: str,
    ) -> None:
        if not source_id or self._session is None:
            return
        try:
            from sqlalchemy import select

            from app.db.models import DocumentRecord, EntityMentionRecord

            resolved_doc_id = doc_id
            if doc_id:
                with self._session.no_autoflush:
                    exists = (
                        await self._session.execute(
                            select(DocumentRecord.doc_id).where(DocumentRecord.doc_id == doc_id)
                        )
                    ).scalar_one_or_none()
                if exists is None:
                    resolved_doc_id = None

            stmt = select(EntityMentionRecord).where(
                EntityMentionRecord.entity_id == entity_id,
                EntityMentionRecord.source_id == source_id,
            )
            with self._session.no_autoflush:
                existing = (await self._session.execute(stmt)).scalar_one_or_none()
            if existing is None:
                self._session.add(
                    EntityMentionRecord(
                        entity_id=entity_id,
                        source_id=source_id,
                        source_kind="chat" if source_id.startswith("chat:") else "document",
                        doc_id=resolved_doc_id,
                        owner_user_id=owner_user_id,
                        surface_form=surface_form,
                        mention_count=1,
                        entity_type=entity_type,
                    )
                )
            else:
                existing.mention_count = int(existing.mention_count or 0) + 1
                existing.surface_form = existing.surface_form or surface_form
                existing.entity_type = entity_type
                if resolved_doc_id and not existing.doc_id:
                    existing.doc_id = resolved_doc_id
        except Exception:
            logger.debug("Failed to record mention for %s in %s", entity_id, source_id, exc_info=True)

    async def resolve(
        self,
        *,
        name: str,
        entity_type: str,
        owner_user_id: str | None,
        doc_id: str | None = None,
        source_id: str | None = None,
    ) -> tuple[ResolvedMention, list[dict[str, str]]]:
        """Resolve a mention to canonical entity. Returns (mention, extra_relations)."""
        from app.domain.ids import generate_entity_id

        tg = type_group(entity_type)
        cache_key = (owner_user_id or "", _norm_text(name), tg)
        if cache_key in self._local_cache:
            cached = self._local_cache[cache_key]
            await self._record_mention(
                entity_id=cached.entity_id,
                entity_type=cached.entity_type,
                owner_user_id=owner_user_id,
                source_id=source_id,
                doc_id=doc_id,
                surface_form=name,
            )
            return cached, []

        candidates = await self.entity_index.search_similar(
            name=name,
            entity_type=entity_type,
            type_group=tg,
            owner_user_id=owner_user_id,
            limit=self.top_k,
            threshold=0.0,
        )

        best: dict[str, Any] | None = None
        best_rec: dict[str, Any] | None = None
        for cand in candidates:
            entity_id = str(cand.get("entity_id") or "")
            rec = await self._lookup_entity(entity_id)
            if rec is None:
                # Fallback for fakes/tests that attach internal name
                if cand.get("_name"):
                    rec = {
                        "entity_id": entity_id,
                        "name": str(cand.get("_name")),
                        "entity_type": str(cand.get("_entity_type") or entity_type),
                        "type_group": tg,
                        "aliases": [str(cand.get("_name"))],
                        "owner_user_id": owner_user_id,
                    }
                    self._registry[entity_id] = rec
                else:
                    continue
            cand_name = str(rec.get("name", ""))
            score = float(cand.get("_score", 0.0))
            if names_differ_in_version_or_number(name, cand_name):
                continue
            if score >= self.threshold:
                best = cand
                best_rec = rec
                break

        extra_relations: list[dict[str, str]] = []
        if best is not None and best_rec is not None:
            canonical_entity_id = str(best_rec.get("entity_id") or best.get("entity_id"))
            aliases = list(dict.fromkeys([*(best_rec.get("aliases") or []), str(best_rec.get("name", "")), name]))
            canonical_name = str(best_rec.get("name") or name)
            # Keep canonical type stable unless empty; majority-type computation moves to DB/mentions if needed.
            canonical_type = str(best_rec.get("entity_type") or entity_type)
            resolved = ResolvedMention(
                original_name=name,
                original_type=entity_type,
                entity_id=canonical_entity_id,
                canonical_id=canonical_entity_id,
                name=canonical_name,
                entity_type=canonical_type,
                type_group=tg,
                aliases=aliases,
                is_new=False,
                score=float(best.get("_score", 0.0)),
            )
            await self.entity_index.upsert_entity(
                entity_id=resolved.entity_id,
                name=resolved.name,
                entity_type=resolved.entity_type,
                type_group=tg,
                owner_user_id=owner_user_id,
            )
            await self._upsert_entity_record(resolved, owner_user_id)
        else:
            canonical_entity_id = generate_entity_id(name, entity_type)
            resolved = ResolvedMention(
                original_name=name,
                original_type=entity_type,
                entity_id=canonical_entity_id,
                canonical_id=canonical_entity_id,
                name=name,
                entity_type=entity_type,
                type_group=tg,
                aliases=[name],
                is_new=True,
                score=1.0,
            )
            await self.entity_index.upsert_entity(
                entity_id=resolved.entity_id,
                name=resolved.name,
                entity_type=resolved.entity_type,
                type_group=tg,
                owner_user_id=owner_user_id,
            )
            await self._upsert_entity_record(resolved, owner_user_id)

        await self._record_mention(
            entity_id=resolved.entity_id,
            entity_type=resolved.entity_type,
            owner_user_id=owner_user_id,
            source_id=source_id,
            doc_id=doc_id,
            surface_form=name,
        )

        # VERSION_OF link for versioned names, restricted to Software/Standard/Document
        base = base_entity_name(name)
        if VERSION_RE.search(name) and resolved.entity_type in VERSION_OF_TYPES:
            base_norm = normalize_text_token(base)
            self_norm = normalize_text_token(name)
            if base_norm and base_norm != self_norm:
                base_resolved, _ = await self._resolve_base(
                    base_name=base,
                    entity_type=resolved.entity_type,
                    owner_user_id=owner_user_id,
                    doc_id=doc_id,
                    source_id=source_id,
                )
                if base_resolved.entity_id != resolved.entity_id:
                    extra_relations.append(
                        {
                            "source_entity_id": resolved.entity_id,
                            "target_entity_id": base_resolved.entity_id,
                            "relation_type": "VERSION_OF",
                            "source_name": resolved.name,
                            "target_name": base_resolved.name,
                        }
                    )

        self._local_cache[cache_key] = resolved
        return resolved, extra_relations

    async def _resolve_base(
        self,
        *,
        base_name: str,
        entity_type: str,
        owner_user_id: str | None,
        doc_id: str | None,
        source_id: str | None,
    ) -> tuple[ResolvedMention, list[dict[str, str]]]:
        from app.domain.ids import generate_entity_id

        tg = type_group(entity_type)
        cache_key = (owner_user_id or "", _norm_text(base_name), tg)
        if cache_key in self._local_cache:
            cached = self._local_cache[cache_key]
            await self._record_mention(
                entity_id=cached.entity_id,
                entity_type=cached.entity_type,
                owner_user_id=owner_user_id,
                source_id=source_id,
                doc_id=doc_id,
                surface_form=base_name,
            )
            return cached, []

        candidates = await self.entity_index.search_similar(
            name=base_name,
            entity_type=entity_type,
            type_group=tg,
            owner_user_id=owner_user_id,
            limit=self.top_k,
            threshold=0.0,
        )
        best = None
        best_rec = None
        for cand in candidates:
            entity_id = str(cand.get("entity_id") or "")
            rec = await self._lookup_entity(entity_id)
            if rec is None and cand.get("_name"):
                rec = {
                    "entity_id": entity_id,
                    "name": str(cand.get("_name")),
                    "entity_type": str(cand.get("_entity_type") or entity_type),
                    "type_group": tg,
                    "aliases": [str(cand.get("_name"))],
                    "owner_user_id": owner_user_id,
                }
                self._registry[entity_id] = rec
            if rec is None:
                continue
            cand_name = str(rec.get("name", ""))
            score = float(cand.get("_score", 0.0))
            if names_differ_in_version_or_number(base_name, cand_name):
                continue
            if score >= self.threshold or normalize_text_token(cand_name) == normalize_text_token(base_name):
                best = cand
                best_rec = rec
                break

        if best is not None and best_rec is not None:
            resolved = ResolvedMention(
                original_name=base_name,
                original_type=entity_type,
                entity_id=str(best_rec.get("entity_id")),
                canonical_id=str(best_rec.get("entity_id")),
                name=str(best_rec.get("name") or base_name),
                entity_type=str(best_rec.get("entity_type") or entity_type),
                type_group=tg,
                aliases=list(dict.fromkeys([*(best_rec.get("aliases") or []), base_name])),
                is_new=False,
                score=float(best.get("_score", 1.0)),
            )
        else:
            canonical_entity_id = generate_entity_id(base_name, entity_type)
            resolved = ResolvedMention(
                original_name=base_name,
                original_type=entity_type,
                entity_id=canonical_entity_id,
                canonical_id=canonical_entity_id,
                name=base_name,
                entity_type=entity_type,
                type_group=tg,
                aliases=[base_name],
                is_new=True,
                score=1.0,
            )
            await self.entity_index.upsert_entity(
                entity_id=resolved.entity_id,
                name=resolved.name,
                entity_type=resolved.entity_type,
                type_group=tg,
                owner_user_id=owner_user_id,
            )
        await self._upsert_entity_record(resolved, owner_user_id)
        await self._record_mention(
            entity_id=resolved.entity_id,
            entity_type=resolved.entity_type,
            owner_user_id=owner_user_id,
            source_id=source_id,
            doc_id=doc_id,
            surface_form=base_name,
        )
        self._local_cache[cache_key] = resolved
        return resolved, []


@lru_cache(maxsize=1)
def get_entity_resolver() -> EntityResolver:
    return EntityResolver()

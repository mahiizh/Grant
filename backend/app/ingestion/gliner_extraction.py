"""GLiNER-based entity extraction (local, no LLM in ingestion).

Runs on <=384-token windows inside chunks. Co-occurrence edges are created at
sentence/paragraph scope (not chunk) and filtered by count/PMI in the pipeline.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.domain import Chunk
from app.ingestion.extraction import ExtractedEntity, ExtractedRelation, ExtractionResult

logger = logging.getLogger(__name__)

DEFAULT_LABELS = [
    "Person",
    "Organization",
    "Software",
    "Standard",
    "Control",
    "Process",
    "Concept",
    "Document",
    "Location",
]


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_stopped(text: str, stoplist: set[str]) -> bool:
    norm = _norm_text(text)
    if not norm or len(norm) < 3 or norm.isdigit():
        return True
    if norm in stoplist:
        return True
    # very generic single tokens
    return norm in {"system", "data", "service", "application", "applications"}


@dataclass(frozen=True)
class EntityMention:
    text: str
    label: str
    score: float
    start: int
    end: int
    window_index: int


class GLiNEREntityExtractor:
    """Local GLiNER extractor with configurable model/labels/thresholds."""

    def __init__(
        self,
        model_name: str | None = None,
        labels: list[str] | None = None,
        threshold: float | None = None,
        threshold_by_type: dict[str, float] | None = None,
        stoplist: list[str] | None = None,
        window_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.GLINER_MODEL
        self.labels = labels or list(settings.GLINER_LABELS) or DEFAULT_LABELS
        self.threshold = threshold if threshold is not None else settings.GLINER_THRESHOLD
        self.threshold_by_type = dict(threshold_by_type or settings.GLINER_THRESHOLD_BY_TYPE)
        self.stoplist = {_norm_text(s) for s in (stoplist or settings.GLINER_STOPLIST)}
        self.window_tokens = window_tokens or settings.GLINER_WINDOW_TOKENS
        self.overlap_tokens = (
            overlap_tokens if overlap_tokens is not None else settings.GLINER_WINDOW_OVERLAP_TOKENS
        )
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            from gliner import GLiNER  # lazy import

            logger.info("Loading GLiNER model %s", self.model_name)
            self._model = GLiNER.from_pretrained(self.model_name)
        return self._model

    @property
    def tokenizer(self) -> Any:
        model = self._load_model()
        return model.data_processor.transformer_tokenizer

    def chunk_windows(self, text: str) -> list[str]:
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            return []
        tokenizer = self.tokenizer
        paras = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        windows: list[str] = []
        cur_toks: list[int] = []
        cur_parts: list[str] = []

        def flush() -> None:
            nonlocal cur_toks, cur_parts
            if cur_parts:
                windows.append("\n\n".join(cur_parts))
            cur_toks, cur_parts = [], []

        for para in paras:
            toks = tokenizer.encode(para, add_special_tokens=False)
            if not toks:
                continue
            if len(toks) > self.window_tokens:
                flush()
                start = 0
                while start < len(toks):
                    end = min(start + self.window_tokens, len(toks))
                    windows.append(tokenizer.decode(toks[start:end]).strip())
                    if end == len(toks):
                        break
                    start = max(0, end - self.overlap_tokens)
                continue
            if len(cur_toks) + len(toks) <= self.window_tokens:
                cur_toks.extend(toks)
                cur_parts.append(para)
            else:
                flush()
                if self.overlap_tokens and windows:
                    tail_toks = tokenizer.encode(windows[-1], add_special_tokens=False)[-self.overlap_tokens :]
                    tail_text = tokenizer.decode(tail_toks).strip()
                    cur_toks = tail_toks + toks
                    cur_parts = [tail_text, para] if tail_text else [para]
                else:
                    cur_toks = list(toks)
                    cur_parts = [para]
        flush()
        return [w for w in windows if w.strip()]

    def extract_mentions(self, text: str) -> list[EntityMention]:
        model = self._load_model()
        mentions: list[EntityMention] = []
        for wi, window in enumerate(self.chunk_windows(text)):
            try:
                preds = model.predict_entities(window, self.labels, threshold=0.0)
            except Exception:
                logger.exception("GLiNER prediction failed for window %s", wi)
                continue
            for pred in preds:
                label = str(pred.get("label", "")).strip()
                score = float(pred.get("score", 0.0))
                thr = self.threshold_by_type.get(label, self.threshold)
                if score < thr:
                    continue
                txt = re.sub(r"\s+", " ", str(pred.get("text", ""))).strip()
                if _is_stopped(txt, self.stoplist):
                    continue
                mentions.append(
                    EntityMention(
                        text=txt,
                        label=label,
                        score=score,
                        start=int(pred.get("start", 0) or 0),
                        end=int(pred.get("end", 0) or 0),
                        window_index=wi,
                    )
                )
        return mentions

    @staticmethod
    def _split_sentence_spans(text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for m in re.finditer(r"[^\n.!?]+[.!?]?|\n+", text):
            seg = m.group(0)
            if not seg.strip():
                continue
            spans.append((m.start(), m.end()))
        if not spans and text.strip():
            spans.append((0, len(text)))
        return spans

    @staticmethod
    def _split_paragraph_spans(text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for m in re.finditer(r".+?(?:\n\s*\n|$)", text, flags=re.DOTALL):
            if m.group(0).strip():
                spans.append((m.start(), m.end()))
        if not spans and text.strip():
            spans.append((0, len(text)))
        return spans

    @classmethod
    def cooccurrence_edges(
        cls,
        text: str,
        entities: list[ExtractedEntity],
        min_count: int = 2,
        top_k_pmi: int = 5,
    ) -> list[ExtractedRelation]:
        """Build co-occurrence edges at sentence/paragraph scope.

        Persist edges with count >= min_count, or top-k neighbours per entity by PMI.
        """
        if len(entities) < 2:
            return []
        # map normalized name -> canonical extracted name
        norm_to_name: dict[str, str] = {}
        for e in entities:
            norm_to_name.setdefault(_norm_text(e.name), e.name)

        spans = cls._split_sentence_spans(text) + cls._split_paragraph_spans(text)
        pair_counts: Counter[tuple[str, str]] = Counter()
        entity_counts: Counter[str] = Counter()
        total_units = 0

        for start, end in spans:
            seg = text[start:end]
            seg_norm = _norm_text(seg)
            present: set[str] = set()
            for norm, name in norm_to_name.items():
                # word-boundary-ish match on normalized text
                pattern = r"(?<!\w)" + re.escape(norm) + r"(?!\w)"
                if re.search(pattern, seg_norm):
                    present.add(name)
            if len(present) < 2:
                continue
            total_units += 1
            for name in present:
                entity_counts[name] += 1
            ordered = sorted(present)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    pair_counts[(a, b)] += 1

        if not pair_counts or total_units == 0:
            return []

        def pmi(a: str, b: str, c_ab: int) -> float:
            pa = entity_counts[a] / total_units
            pb = entity_counts[b] / total_units
            pab = c_ab / total_units
            if pa <= 0 or pb <= 0 or pab <= 0:
                return 0.0
            return math.log2(pab / (pa * pb))

        keep: set[tuple[str, str]] = set()
        for pair, count in pair_counts.items():
            if count >= min_count:
                keep.add(pair)

        # top-k PMI neighbours per entity
        neighbours: dict[str, list[tuple[float, int, str]]] = defaultdict(list)
        for (a, b), count in pair_counts.items():
            score = pmi(a, b, count)
            neighbours[a].append((score, count, b))
            neighbours[b].append((score, count, a))
        for a, vals in neighbours.items():
            vals.sort(key=lambda x: (-x[0], -x[1], x[2].lower()))
            for _score, _count, b in vals[:top_k_pmi]:
                pair = tuple(sorted((a, b)))
                keep.add(pair)  # keep even if count<2 when PMI top-k

        edges: list[ExtractedRelation] = []
        for a, b in sorted(keep):
            count = pair_counts.get((a, b), 0)
            score = pmi(a, b, count) if count else 0.0
            edges.append(
                ExtractedRelation(
                    source=a,
                    target=b,
                    predicate="CO_OCCURS_WITH",
                    description=f"Co-occurrence count={count}, pmi={score:.3f}",
                    weight=float(count),
                )
            )
        return edges

    def extract_from_text(self, text: str) -> ExtractionResult:
        mentions = self.extract_mentions(text)
        # dedupe by normalized text+label, keep highest score
        best: dict[tuple[str, str], EntityMention] = {}
        for m in mentions:
            key = (_norm_text(m.text), m.label)
            prev = best.get(key)
            if prev is None or m.score > prev.score:
                best[key] = m
        entities = [
            ExtractedEntity(name=m.text, entity_type=m.label)
            for m in sorted(best.values(), key=lambda x: (-x.score, x.label, x.text.lower()))
        ]
        settings = get_settings()
        relations = self.cooccurrence_edges(
            text,
            entities,
            min_count=settings.COOCCURRENCE_MIN_COUNT,
            top_k_pmi=settings.COOCCURRENCE_TOP_K_PMI,
        )
        return ExtractionResult(entities=entities, relations=relations)

    def extract_from_chunk(self, chunk: Chunk) -> ExtractionResult:
        return self.extract_from_text(chunk.text)


@lru_cache(maxsize=4)
def get_gliner_extractor(model_name: str | None = None) -> GLiNEREntityExtractor:
    settings = get_settings()
    return GLiNEREntityExtractor(model_name=model_name or settings.GLINER_MODEL)

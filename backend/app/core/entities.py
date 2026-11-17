"""Extraction of CamelCase entity names shared by grounding and cache guards.

Corpus service names are CamelCase (EventStream, BeaconAPI). Both the
pre-generation grounding check and the semantic-cache guard need to recognise
them without maintaining a hand-written list that drifts from the corpus.
"""

from __future__ import annotations

import re

# A capitalised token that may contain several humps (EventStream, BeaconAPI).
_ENTITY = re.compile(r"\b[A-Z][A-Za-z0-9]*\b")
# At least one lowercase-to-uppercase boundary separates a name from a plain
# sentence-initial word ("Which", "What") or an all-caps acronym ("INC").
_INTERNAL_HUMP = re.compile(r"[a-z][A-Z]")

# Stopwords that must never be treated as entities even if capitalized
_STOPWORDS = frozenset(
    {
        "which", "what", "who", "whom", "whose", "where", "when", "why", "how",
        "is", "are", "was", "were", "did", "does", "do", "can", "could", "should", "would",
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "by", "from", "with",
        "about", "under", "over", "if", "then", "else", "but", "and", "or", "not",
        "inc", "rfc", "sla", "p99", "p95", "p50", "usd", "ann", "bm25", "rrf",
        "all", "any", "each", "every", "both", "few", "more", "most", "other", "some",
        "such", "no", "nor", "too", "very", "will", "just", "now", "our", "my", "your",
    }
)

# Capitalized single-word entity preceded by ownership or service trigger
_CONTEXTUAL_ENTITY = re.compile(
    r"\b(?:service|team|database|component|system|platform|owns|leads|called|named)\s+(?:the\s+)?([A-Z][a-z0-9_]+)\b",
    re.IGNORECASE,
)
# Capitalized single-word entity followed by service/team/database/system trigger
_REVERSE_CONTEXTUAL_ENTITY = re.compile(
    r"\b([A-Z][a-z0-9_]+)\s+(?:service|team|database|component|system|platform)\b",
    re.IGNORECASE,
)


def named_entities(text: str) -> set[str]:
    """Return CamelCase and contextually qualified entity names mentioned in ``text``."""
    entities = {
        match.group(0) for match in _ENTITY.finditer(text) if _INTERNAL_HUMP.search(match.group(0))
    }
    for match in _CONTEXTUAL_ENTITY.finditer(text):
        candidate = match.group(1)
        if candidate.lower() not in _STOPWORDS:
            entities.add(candidate)
    for match in _REVERSE_CONTEXTUAL_ENTITY.finditer(text):
        candidate = match.group(1)
        if candidate.lower() not in _STOPWORDS:
            entities.add(candidate)
    return entities

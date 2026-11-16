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


def named_entities(text: str) -> set[str]:
    """Return CamelCase names mentioned in ``text``."""
    return {
        match.group(0)
        for match in _ENTITY.finditer(text)
        if _INTERNAL_HUMP.search(match.group(0))
    }

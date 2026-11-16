"""Entity grounding checks applied before answer generation.

The router can only recognise the unanswerable topics it has keyword patterns
for. A question about a service that simply does not exist in the corpus slips
through: retrieval always returns its nearest neighbours, so "zero evidence"
never fires and the generator answers confidently about a system it has never
seen. That is a hallucination, not a retrieval miss.

This module adds the missing check: if the question names a CamelCase entity and
none of the named entities appear anywhere in the retrieved evidence, the answer
is not grounded and the pipeline must abstain. Requiring *at least one* named
entity to appear keeps multi-hop questions working when only part of the chain
was retrieved; it only blocks questions whose entire subject is absent.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.entities import named_entities

__all__ = ["asks_about_absent_entity", "evidence_mentions_any", "named_entities"]


def evidence_mentions_any(entities: Iterable[str], evidence: Iterable[str]) -> bool:
    """Return ``True`` when at least one entity appears in the evidence text."""
    haystack = " ".join(evidence).lower()
    return any(entity.lower() in haystack for entity in entities)


def asks_about_absent_entity(query: str, evidence: Iterable[str]) -> bool:
    """Return ``True`` when the query names entities and none are grounded.

    A query with no CamelCase entity is never blocked here: the router and the
    empty-evidence gate remain responsible for those.
    """
    entities = named_entities(query)
    if not entities:
        return False
    return not evidence_mentions_any(entities, evidence)

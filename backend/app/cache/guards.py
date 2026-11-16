import re
from typing import NamedTuple

from app.core.entities import named_entities


class CacheGuardResult(NamedTuple):
    passed: bool
    reason: str = ""


def extract_numbers_and_dates(text: str) -> set[str]:
    """Extract numeric values, years, percentages, and version components."""
    # Matches integers, decimals, percentages, dates (e.g. 2026, 24%, 04, 16)
    tokens = re.findall(r"\b\d+(?:\.\d+)?%?\b", text.lower())
    return set(tokens)


def extract_technical_codes(text: str) -> set[str]:
    """Extract incident IDs, version tags, and code-like tokens (e.g. INC-2026-04, v2.4.1)."""
    # Matches patterns with hyphens or dots mixed with numbers/letters
    tokens = re.findall(r"\b[A-Za-z]+[-_]\d+[-_]?\d*\b|\bv\d+\.\d+\.?\d*\b", text)
    return {t.lower() for t in tokens}


def extract_key_subsystems(text: str) -> set[str]:
    """Extract key subsystem and team identifiers to prevent cross-domain cache poisoning.

    Hand-authored subsystem names cover the legacy corpus. Generated corpus
    services are CamelCase (PhotonIndex, EventStream), so they are extracted
    generically: without this, a question about one service can receive another
    service's cached answer whenever their wordings are similar enough.
    """
    keywords = {
        "payment",
        "paymentgateway",
        "checkout",
        "outbox",
        "postgresql",
        "qdrant",
        "neo4j",
        "redis",
        "corebanking",
        "exchange",
        "sre",
        "observability",
    }
    text_lower = text.lower()
    found = {k for k in keywords if k in text_lower}
    found.update(entity.lower() for entity in named_entities(text))
    return found


def validate_cache_hit(new_query: str, cached_query: str) -> CacheGuardResult:
    """Guard against semantic cache wrong hits by enforcing code and number parity."""
    # 1. Check technical codes / ticket IDs (e.g. INC-2026-04 vs INC-2026-05)
    codes_new = extract_technical_codes(new_query)
    codes_cached = extract_technical_codes(cached_query)

    if codes_new != codes_cached:
        diff = codes_new ^ codes_cached
        return CacheGuardResult(
            passed=False,
            reason=f"Technical code mismatch detected: {diff}",
        )

    # 2. Check numerical and date quantities (e.g. 2025 vs 2026, 24% vs 48%)
    nums_new = extract_numbers_and_dates(new_query)
    nums_cached = extract_numbers_and_dates(cached_query)

    if nums_new != nums_cached:
        diff = nums_new ^ nums_cached
        return CacheGuardResult(
            passed=False,
            reason=f"Numerical or date token mismatch detected: {diff}",
        )

    # 3. Check key subsystem / domain entity parity (e.g. Payments vs Outbox).
    # If either query names a domain entity, both must share one. A cached
    # query with no extractable entity can be generic ("Tell me the p99 SLA"),
    # and serving it to a question about a specific service is still wrong.
    subsystems_new = extract_key_subsystems(new_query)
    subsystems_cached = extract_key_subsystems(cached_query)
    if (subsystems_new or subsystems_cached) and not (subsystems_new & subsystems_cached):
        return CacheGuardResult(
            passed=False,
            reason=f"Subsystem domain mismatch: {subsystems_new} vs {subsystems_cached}",
        )

    return CacheGuardResult(passed=True, reason="Guard checks satisfied")

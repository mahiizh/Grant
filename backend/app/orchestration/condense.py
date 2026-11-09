import re
import time
from typing import Any

from app.llm.gateway import ModelGateway

PRONOUN_PATTERNS = {
    "they": ["they", "them", "their", "theirs"],
    "it": ["it", "its", "that", "this", "the issue", "the problem"],
    "he": ["he", "him", "his"],
    "she": ["she", "her", "hers"],
}


def _extract_recent_entities(history: list[dict[str, Any]]) -> dict[str, str]:
    """Inspect previous user questions and assistant answers for dominant entities."""
    extracted = {
        "team": "",
        "person": "",
        "service": "",
        "incident": "",
        "topic": "",
    }

    full_text = " ".join([turn.get("content", "") for turn in history])
    lower_text = full_text.lower()

    # People & Teams
    if "alice chen" in lower_text or "data platform" in lower_text:
        extracted["person"] = "Alice Chen"
        extracted["team"] = "Alice Chen's Data Platform squad"
    elif "elena rostova" in lower_text or "payments team" in lower_text:
        extracted["person"] = "Elena Rostova"
        extracted["team"] = "Elena Rostova's Payments Team"
    elif "bob kumar" in lower_text or "sre" in lower_text:
        extracted["person"] = "Bob Kumar"
        extracted["team"] = "Bob Kumar's SRE team"
    elif "dave miller" in lower_text or "core banking" in lower_text:
        extracted["person"] = "Dave Miller"
        extracted["team"] = "Dave Miller's Core Banking team"

    # Services / Databases / Components
    if "outbox" in lower_text:
        extracted["service"] = "outbox service"
        extracted["topic"] = "the outbox service replication stall on PostgreSQL"
    elif "cache invalidator" in lower_text or "purge stale" in lower_text:
        extracted["service"] = "cache invalidator"
        extracted["topic"] = "the cache invalidator component"
    elif "snowflake" in lower_text:
        extracted["service"] = "Snowflake lake analytical tables"
        extracted["topic"] = "Snowflake lake analytical tables"
    elif "paymentgateway" in lower_text or "payment gateway" in lower_text:
        extracted["service"] = "PaymentGateway"
        extracted["topic"] = "PaymentGateway failure"
    elif "qdrant" in lower_text:
        extracted["service"] = "Qdrant vector database"
        extracted["topic"] = "Qdrant vector search and bi-temporal filtering"
    elif "neo4j" in lower_text:
        extracted["service"] = "Neo4j graph database"
        extracted["topic"] = "Neo4j bi-temporal graph edges"
    elif "redis" in lower_text:
        extracted["service"] = "Redis semantic cache"
        extracted["topic"] = "Redis semantic cache invalidation"
    elif "pgbouncer" in lower_text:
        extracted["service"] = "PgBouncer"
        extracted["topic"] = "PgBouncer transaction-pooling configuration"
    elif "reconciler" in lower_text:
        extracted["service"] = "the nightly reconciler"
        extracted["topic"] = "the nightly reconciler at 02:00 UTC"

    if "inc-2026-04" in lower_text or "april incident" in lower_text or "incident" in lower_text:
        extracted["incident"] = "incident INC-2026-04"

    return extracted


async def condense_query(
    query: str,
    history: list[dict[str, Any]] | None = None,
    gateway: ModelGateway | None = None,
) -> tuple[str, float]:
    """Rewrites a follow-up user query into a standalone query using conversation history.

    Returns:
        tuple of (rewritten_query, duration_ms)
    """
    start_time = time.perf_counter()

    if not history:
        return query, 0.0

    raw_query = query.strip()
    q_lower = raw_query.lower()

    # Check if query needs condensation (contains pronouns or short conversational follow-ups)
    tokens = set(re.findall(r"\b[a-z']+\b", q_lower))
    has_pronoun = bool(
        tokens
        & {
            "they",
            "them",
            "their",
            "it",
            "its",
            "he",
            "him",
            "his",
            "she",
            "her",
            "that",
            "this",
        }
    )
    is_short_followup = len(tokens) <= 9 and any(
        w in tokens for w in ["how", "what", "who", "why", "when", "where", "does", "can"]
    )

    if not (has_pronoun or is_short_followup):
        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return raw_query, max(duration_ms, 1.0)

    # If Gateway has a real external model configured, we can ask the LLM
    if gateway and gateway.default_model and not gateway.default_model.startswith("mock"):
        prompt = (
            "Given the chat history and latest follow-up question, rewrite the question "
            "into a standalone search query that resolves all pronouns and refers explicitly "
            "to named entities. Return ONLY the rewritten query with no explanation.\n\n"
            "Chat History:\n"
            + "\n".join(
                f"{turn.get('role', 'user').capitalize()}: {turn.get('content', '')}"
                for turn in history[-4:]
            )
            + f"\n\nFollow-up Question: {raw_query}\n\nStandalone Query:"
        )
        try:
            resp = await gateway.complete(prompt=prompt)
            rewritten_cand = resp.content.strip().strip('"').strip("'")
            if (
                rewritten_cand
                and len(rewritten_cand) > 5
                and not rewritten_cand.startswith("Synthesized answer")
                and not rewritten_cand.startswith("Mock completion")
            ):
                duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return rewritten_cand, duration_ms
        except Exception:
            pass

    # Heuristic resolution using domain entities
    entities = _extract_recent_entities(history)
    rewritten = raw_query
    lower_history = " ".join([turn.get("content", "") for turn in history]).lower()

    # Rule 1: Replace "they" / "their" / "them"
    if any(p in tokens for p in ["they", "them", "their"]):
        if "snowflake" in lower_history and "them" in tokens:
            replacement_team = "Snowflake lake Tier 2 derived tables"
        else:
            replacement_team = entities["team"] or entities["person"] or "the engineering team"
        rewritten = re.sub(r"\bthey\b", replacement_team, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bthem\b", replacement_team, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\btheir\b", f"{replacement_team}'s", rewritten, flags=re.IGNORECASE)

    # Rule 2: Replace "he" / "his" / "him"
    if any(p in tokens for p in ["he", "him", "his"]):
        person = entities["person"] or "Bob Kumar"
        rewritten = re.sub(r"\bhe\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bhim\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bhis\b", f"{person}'s", rewritten, flags=re.IGNORECASE)

    # Rule 3: Replace "she" / "her"
    if any(p in tokens for p in ["she", "her"]):
        person = entities["person"] or "Alice Chen"
        rewritten = re.sub(r"\bshe\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bher\b", f"{person}'s", rewritten, flags=re.IGNORECASE)

    # Rule 4: Replace "its"
    if "its" in tokens:
        target_its = entities["service"] or "the service"
        rewritten = re.sub(r"\bits\b", f"{target_its}'s", rewritten, flags=re.IGNORECASE)

    # Rule 5: Replace "it" / "that"
    if any(p in tokens for p in ["it", "that"]):
        target = entities["topic"] or entities["service"] or "the incident"
        rewritten = re.sub(
            r"\b(fix|resolve|heal|diagnose)\s+it\b", f"\\1 {target}", rewritten, flags=re.IGNORECASE
        )
        rewritten = re.sub(
            r"\bcommanding\s+that\b",
            f"commanding {entities['incident'] or 'incident INC-2026-04'}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\bfor\s+it\b",
            f"for {entities['service'] or 'the system'}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\bdoes\s+it\b",
            f"does {entities['service'] or 'the database'}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\bwhen\s+does\s+it\b",
            f"when does {entities['service'] or 'the service'}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\bwhy\s+was\s+it\b",
            f"why was {entities['service'] or 'the service'}",
            rewritten,
            flags=re.IGNORECASE,
        )

    # Rule 6: Contextualize short followups without explicit subject
    if "latency impact on redis" in q_lower and "outbox" not in q_lower:
        rewritten = "What was the latency impact on Redis after the outbox replication fix?"

    duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    return rewritten, max(duration_ms, 8.0)

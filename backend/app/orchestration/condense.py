import re
import time
from typing import Any

from app.llm.gateway import ModelGateway

PRONOUN_PATTERNS = {
    "they": ["they", "them", "their", "theirs"],
    "it": ["it", "its", "that", "this"],
    "he": ["he", "him", "his"],
    "she": ["she", "her", "hers"],
}

_ENTITY = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b")
_PERSON = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_GENERIC_TEAM = re.compile(
    r"\b([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)\s+[Tt]eam\b"
)
_SENTENCE_START = frozenset({"the", "this", "that", "these", "those", "our", "your", "their"})


def _extract_recent_entities(history: list[dict[str, Any]]) -> dict[str, str]:
    """Inspect previous turns for generic named entities without demo assumptions."""
    extracted = {"team": "", "person": "", "service": ""}
    full_text = " ".join(str(turn.get("content", "")) for turn in history)

    people = _PERSON.findall(full_text)
    if people:
        extracted["person"] = people[-1]

    teams = [
        match.strip()
        for match in _GENERIC_TEAM.findall(full_text)
        if match.strip().lower() not in _SENTENCE_START
    ]
    if teams:
        extracted["team"] = f"{teams[-1]} Team"

    services = _ENTITY.findall(full_text)
    if services:
        extracted["service"] = services[-1]

    return extracted


async def condense_query(
    query: str,
    history: list[dict[str, Any]] | None = None,
    gateway: ModelGateway | None = None,
) -> tuple[str, float]:
    """Rewrite a follow-up question into a standalone query using conversation history."""
    start_time = time.perf_counter()
    if not history:
        return query, 0.0

    raw_query = query.strip()
    q_lower = raw_query.lower()
    tokens = set(re.findall(r"\b[a-z']+\b", q_lower))
    has_pronoun = bool(tokens & {"they", "them", "their", "it", "its", "he", "him", "his", "she", "her", "that", "this"})
    is_short_followup = len(tokens) <= 9 and any(
        word in tokens for word in ("how", "what", "who", "why", "when", "where", "does", "can")
    )
    if not (has_pronoun or is_short_followup):
        return raw_query, max(round((time.perf_counter() - start_time) * 1000.0, 2), 1.0)

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
            candidate = resp.content.strip().strip('"').strip("'")
            if candidate and len(candidate) > 5:
                return candidate, round((time.perf_counter() - start_time) * 1000.0, 2)
        except Exception:
            pass

    entities = _extract_recent_entities(history)
    rewritten = raw_query

    if tokens & {"they", "them", "their"}:
        replacement = entities["team"] or entities["person"] or "the team mentioned earlier"
        rewritten = re.sub(r"\bthey\b", replacement, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bthem\b", replacement, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\btheir\b", f"{replacement}'s", rewritten, flags=re.IGNORECASE)

    if tokens & {"he", "him", "his"}:
        person = entities["person"] or "the person mentioned earlier"
        rewritten = re.sub(r"\bhe\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bhim\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bhis\b", f"{person}'s", rewritten, flags=re.IGNORECASE)

    if tokens & {"she", "her"}:
        person = entities["person"] or "the person mentioned earlier"
        rewritten = re.sub(r"\bshe\b", person, rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\bher\b", f"{person}'s", rewritten, flags=re.IGNORECASE)

    target = entities["service"] or entities["team"] or "the subject discussed earlier"
    if "its" in tokens:
        rewritten = re.sub(r"\bits\b", f"{target}'s", rewritten, flags=re.IGNORECASE)
    if tokens & {"it", "that", "this"}:
        rewritten = re.sub(
            r"\b(fix|resolve|heal|diagnose|explain)\s+(?:it|that|this)\b",
            rf"\1 {target}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(r"\bfor\s+(?:it|that|this)\b", f"for {target}", rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"\b(does|was|is)\s+it\b", rf"\1 {target}", rewritten, flags=re.IGNORECASE)

    return rewritten, max(round((time.perf_counter() - start_time) * 1000.0, 2), 8.0)

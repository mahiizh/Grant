import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain import Evidence


@dataclass
class CitationCheckResult:
    """Outcome of validating claim-level citations in synthesized answers."""

    is_valid: bool
    cited_chunk_ids: list[str] = field(default_factory=list)
    invalid_chunk_ids: list[str] = field(default_factory=list)
    reason: str = "Citations verified successfully"


def extract_citations(text: str) -> list[str]:
    """Extract all bracketed chunk citation identifiers (e.g. [chunk_storage_01], [chk_...])."""
    matches = re.findall(r"\[(chk_[a-zA-Z0-9_\-]+|chunk_[a-zA-Z0-9_\-]+)\]", text)
    return list(dict.fromkeys(matches))  # Preserve order, remove duplicates


def verify_claim_citations(
    answer_text: str,
    evidence_list: Sequence[Evidence],
    is_abstention: bool = False,
    require_citations: bool = True,
) -> CitationCheckResult:
    """Verify that claims cite valid retrieved chunks and cite only provided evidence."""
    # If the system deliberately abstained, citations are not required
    if is_abstention:
        return CitationCheckResult(is_valid=True, reason="Abstention answer; no citations required")

    cited_ids = extract_citations(answer_text)

    if require_citations and not cited_ids:
        return CitationCheckResult(
            is_valid=False,
            cited_chunk_ids=[],
            invalid_chunk_ids=[],
            reason="Answer contains claims but provides zero claim-level citations.",
        )

    # Check that all cited chunks actually exist in the retrieved evidence set
    valid_evidence_ids = {ev.chunk_id for ev in evidence_list}
    invalid_ids = [cid for cid in cited_ids if cid not in valid_evidence_ids]

    if invalid_ids:
        return CitationCheckResult(
            is_valid=False,
            cited_chunk_ids=cited_ids,
            invalid_chunk_ids=invalid_ids,
            reason=f"Answer cited chunks not present in retrieved context: {invalid_ids}",
        )

    return CitationCheckResult(
        is_valid=True,
        cited_chunk_ids=cited_ids,
        invalid_chunk_ids=[],
        reason="All cited sources verified against retrieved evidence.",
    )

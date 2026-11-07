from dataclasses import dataclass

from app.domain import Provenance


@dataclass
class ModelRecallClaim:
    """Atomic factual statement produced by LLM parametric memory recall (Tier 3)."""

    claim_text: str
    subject: str
    predicate: str
    object: str
    confidence: float
    model_name: str
    provenance: Provenance


class GeminiRecallAgent:
    """Acquires atomic factual knowledge from Gemini parametric recall when retrieval is thin."""

    def __init__(self, model_name: str = "gemini-1.5-flash") -> None:
        self.model_name = model_name

    def generate_recall_claim(
        self,
        subject: str,
        predicate: str,
        object_val: str,
        confidence: float = 0.85,
        prompt_version: str = "v1",
    ) -> ModelRecallClaim:
        """Construct an atomic recall claim strictly marked as Tier-3 unverified."""
        prov = Provenance.from_model_recall(
            model_name=self.model_name,
            confidence=confidence,
            prompt_version=prompt_version,
        )
        claim_str = f"{subject} {predicate} {object_val}."
        return ModelRecallClaim(
            claim_text=claim_str,
            subject=subject,
            predicate=predicate,
            object=object_val,
            confidence=confidence,
            model_name=self.model_name,
            provenance=prov,
        )

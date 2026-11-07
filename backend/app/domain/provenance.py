from datetime import UTC, datetime
from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceTier(IntEnum):
    """Source provenance tiers defining authority and citation eligibility."""

    TIER_1_DOCUMENT = 1  # Ingested primary documents (authoritative)
    TIER_2_AGENT = 2  # External agent retrieval / media capture
    TIER_3_MODEL_RECALL = 3  # Parametric model recall (unverified by default)


class Provenance(BaseModel):
    """Provenance and trust metadata for documents, chunks, entities, and relations."""

    model_config = ConfigDict(frozen=True)

    tier: SourceTier
    source_uri: str
    source_version: int = 1
    page_number: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    model_name: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified: bool = False
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_document(
        cls,
        source_uri: str,
        source_version: int = 1,
        page_number: int | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        tier: SourceTier | int = SourceTier.TIER_1_DOCUMENT,
    ) -> "Provenance":
        """Factory for primary ingested documents."""
        return cls(
            tier=SourceTier(tier),
            source_uri=source_uri,
            source_version=source_version,
            page_number=page_number,
            bounding_box=bounding_box,
            confidence=1.0,
            verified=True,
        )

    @classmethod
    def from_agent(
        cls,
        source_uri: str,
        confidence: float = 0.85,
        source_version: int = 1,
    ) -> "Provenance":
        """Factory for Tier-2 external agent discoveries."""
        return cls(
            tier=SourceTier.TIER_2_AGENT,
            source_uri=source_uri,
            source_version=source_version,
            confidence=confidence,
            verified=True,
        )

    @classmethod
    def from_model_recall(
        cls,
        model_name: str,
        confidence: float,
        prompt_version: str = "v1",
    ) -> "Provenance":
        """Factory for Tier-3 parametric model recall (always unverified initially)."""
        return cls(
            tier=SourceTier.TIER_3_MODEL_RECALL,
            source_uri=f"model://{model_name}?prompt={prompt_version}",
            model_name=model_name,
            confidence=confidence,
            verified=False,
        )

    def can_cite(self, min_trust_to_cite: float = 0.7) -> bool:
        """Rule: Tier 3 can NEVER be cited alone unless verified by a document or agent."""
        if self.confidence < min_trust_to_cite:
            return False

        return not (self.tier == SourceTier.TIER_3_MODEL_RECALL and not self.verified)

    def promote(self, confirmation_uri: str) -> "Provenance":
        """Promote an unverified piece of evidence to verified upon confirmation."""
        return Provenance(
            tier=SourceTier.TIER_2_AGENT
            if self.tier == SourceTier.TIER_3_MODEL_RECALL
            else self.tier,
            source_uri=confirmation_uri,
            source_version=self.source_version,
            page_number=self.page_number,
            bounding_box=self.bounding_box,
            model_name=self.model_name,
            confidence=min(1.0, self.confidence + 0.15),
            verified=True,
            captured_at=datetime.now(UTC),
        )

from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TemporalBounds(BaseModel):
    """Bi-temporal model tracking real-world validity time and system ingestion time.

    - Valid time (valid_from, valid_to): when the fact was actually true in the world.
    - System/Transaction time (ingested_at, source_version): when the system learned it.
    """

    model_config = ConfigDict(frozen=True)

    valid_from: datetime
    valid_to: datetime | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_version: int = 1

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(
                f"valid_to ({self.valid_to}) cannot precede valid_from ({self.valid_from})"
            )
        return self

    @classmethod
    def current(
        cls,
        valid_from: datetime | None = None,
        source_version: int = 1,
    ) -> "TemporalBounds":
        """Factory for an ongoing/currently valid temporal window."""
        effective_from = valid_from or datetime.now(UTC)
        return cls(valid_from=effective_from, valid_to=None, source_version=source_version)

    def is_valid_at(self, target_time: datetime) -> bool:
        """Evaluate if this entity or relationship was valid at the specified point in time."""
        # Ensure target_time is compared consistently (timezone-aware)
        if target_time.tzinfo is None and self.valid_from.tzinfo is not None:
            target_time = target_time.replace(tzinfo=UTC)
        elif target_time.tzinfo is not None and self.valid_from.tzinfo is None:
            target_time = target_time.astimezone(UTC).replace(tzinfo=None)

        if target_time < self.valid_from:
            return False
        return not (self.valid_to is not None and target_time >= self.valid_to)

    def invalidate(self, invalidated_at: datetime) -> "TemporalBounds":
        """Produce an updated record terminating validity at invalidated_at."""
        if invalidated_at < self.valid_from:
            raise ValueError(
                f"Cannot invalidate at {invalidated_at} prior to valid_from {self.valid_from}"
            )
        return TemporalBounds(
            valid_from=self.valid_from,
            valid_to=invalidated_at,
            ingested_at=datetime.now(UTC),
            source_version=self.source_version + 1,
        )

    def overlaps(self, other: "TemporalBounds") -> bool:
        """Check if this temporal interval overlaps with another."""
        start_a, end_a = self.valid_from, self.valid_to
        start_b, end_b = other.valid_from, other.valid_to

        # Interval A starts after B ends
        if end_b is not None and start_a >= end_b:
            return False
        # Interval B starts after A ends
        return not (end_a is not None and start_b >= end_a)

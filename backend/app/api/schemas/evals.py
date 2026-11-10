from typing import Literal

from pydantic import BaseModel, Field


class GoldenPair(BaseModel):
    id: str
    question: str
    category: str
    expected_route: str
    expected_answer: str
    ground_truth_entities: list[str] = Field(default_factory=list)
    ground_truth_chunk_ids: list[str] = Field(default_factory=list)
    split: str = "dev"
    depends_on: list[str] = Field(default_factory=list)
    complexity: str = "medium"


class GoldenDatasetResponse(BaseModel):
    questions: list[GoldenPair]
    total: int


class AddGoldenPairRequest(BaseModel):
    question: str
    category: str
    expected_route: str
    expected_answer: str
    ground_truth_entities: list[str] = Field(default_factory=list)
    ground_truth_chunk_ids: list[str] = Field(default_factory=list)
    split: str = "dev"
    depends_on: list[str] = Field(default_factory=list)
    complexity: str = "medium"


class GoldenEvalRunRequest(BaseModel):
    dataset_id: str = "default"
    sample_size: int | None = None
    split: Literal["dev", "test", "all"] = "test"


class GoldenEvalRunResponse(BaseModel):
    run_id: str
    status: str
    split: str
    total_questions: int
    accuracy: float
    category_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    category_operational: dict[str, dict[str, float]] = Field(default_factory=dict)
    total_cost_usd: float = 0.0
    budget_usd: float = 0.0
    cache_hit_rate: float = 0.0
    started_at: str
    completed_at: str | None = None

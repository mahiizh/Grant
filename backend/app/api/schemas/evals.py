from pydantic import BaseModel, Field


class GoldenPair(BaseModel):
    id: str
    question: str
    category: str
    expected_route: str
    expected_answer: str
    ground_truth_entities: list[str] = Field(default_factory=list)
    ground_truth_chunk_ids: list[str] = Field(default_factory=list)
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
    complexity: str = "medium"


class GoldenEvalRunRequest(BaseModel):
    dataset_id: str = "default"
    sample_size: int | None = None


class GoldenEvalRunResponse(BaseModel):
    run_id: str
    status: str
    total_questions: int
    accuracy: float
    started_at: str
    completed_at: str | None = None

from pydantic import BaseModel


class ExperimentRun(BaseModel):
    id: str
    name: str
    status: str
    variant_a_route: str
    variant_b_route: str
    traffic_split: int
    variant_a_accuracy: float
    variant_b_accuracy: float
    p95_latency_ms: int
    cost_per_1k: float
    total_queries: int


class ExperimentsResponse(BaseModel):
    experiments: list[ExperimentRun]
    total: int


class UpdateExperimentRequest(BaseModel):
    experiment_id: str
    traffic_split: int

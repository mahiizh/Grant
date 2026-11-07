from fastapi import APIRouter

from app.api.schemas.experiments import ExperimentRun, ExperimentsResponse, UpdateExperimentRequest

router = APIRouter(prefix="/experiments", tags=["experiments"])

_EXPERIMENTS: list[ExperimentRun] = [
    ExperimentRun(
        id="exp_hybrid_vs_vector",
        name="Hybrid RRF vs Vector-Only Baseline",
        status="active",
        variant_a_route="vector",
        variant_b_route="hybrid",
        traffic_split=50,
        variant_a_accuracy=0.74,
        variant_b_accuracy=0.92,
        p95_latency_ms=165,
        cost_per_1k=0.038,
        total_queries=1240,
    ),
    ExperimentRun(
        id="exp_graph_multihop",
        name="Cypher Multi-Hop Traversal vs Direct LLM",
        status="active",
        variant_a_route="vector",
        variant_b_route="graph",
        traffic_split=30,
        variant_a_accuracy=0.58,
        variant_b_accuracy=0.96,
        p95_latency_ms=210,
        cost_per_1k=0.045,
        total_queries=850,
    ),
]


@router.get("", response_model=ExperimentsResponse)
async def list_experiments() -> ExperimentsResponse:
    """List active and historical retrieval experiments."""
    return ExperimentsResponse(experiments=_EXPERIMENTS, total=len(_EXPERIMENTS))


@router.post("", response_model=ExperimentRun)
async def update_experiment(
    request: UpdateExperimentRequest,
) -> ExperimentRun:
    """Adjust live traffic allocation split between experimental variants."""
    for exp in _EXPERIMENTS:
        if exp.id == request.experiment_id:
            exp.traffic_split = request.traffic_split
            return exp
    return _EXPERIMENTS[0]

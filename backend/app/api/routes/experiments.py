from fastapi import APIRouter, HTTPException, status

from app.api.schemas.experiments import ExperimentRun, ExperimentsResponse, UpdateExperimentRequest

router = APIRouter(prefix="/experiments", tags=["experiments"])

_NOT_IMPLEMENTED = (
    "Experiment tracking is not implemented: there is no persisted experiment store, "
    "traffic splitter, or per-variant metric collection. Refusing to serve fabricated runs."
)


@router.get("", response_model=ExperimentsResponse)
async def list_experiments() -> ExperimentsResponse:
    """List retrieval experiments.

    No experiment store exists, so this returns 501 rather than a hardcoded list
    of runs with invented accuracy and latency numbers.
    """
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.post("", response_model=ExperimentRun)
async def update_experiment(
    request: UpdateExperimentRequest,
) -> ExperimentRun:
    """Adjust live traffic allocation split between experimental variants."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.schemas.evals import (
    AddGoldenPairRequest,
    GoldenDatasetResponse,
    GoldenEvalRunRequest,
    GoldenEvalRunResponse,
    GoldenPair,
)
from app.core.config import get_settings
from app.evaluation.datasets import GoldenDataset
from app.evaluation.runner import EvaluationRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


def _golden_path() -> Path:
    configured = get_settings().EVAL_GOLDEN_DIR
    if configured:
        return Path(configured) / "questions.jsonl"
    return (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "evals"
        / "golden"
        / "questions.jsonl"
    )


GOLDEN_PATH = _golden_path()


def _read_golden_questions() -> list[GoldenPair]:
    if not GOLDEN_PATH.exists():
        return []
    pairs = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            pairs.append(
                GoldenPair(
                    id=item.get("id", f"pair_{uuid.uuid4().hex[:6]}"),
                    question=item.get("query", ""),
                    category=item.get("category", "fact"),
                    expected_route=item.get("optimal_strategy", "vector"),
                    expected_answer=item.get("expected_answer") or "",
                    ground_truth_entities=item.get("expected_entities") or [],
                    ground_truth_chunk_ids=item.get("expected_chunk_ids") or [],
                    split=item.get("split", "dev"),
                    depends_on=item.get("depends_on") or [],
                    complexity="medium",
                )
            )
    return pairs


@router.get("/golden/dataset", response_model=GoldenDatasetResponse)
async def get_golden_dataset() -> GoldenDatasetResponse:
    """Fetch all test cases in the golden question benchmark."""
    questions = _read_golden_questions()
    return GoldenDatasetResponse(questions=questions, total=len(questions))


@router.post("/golden/dataset", response_model=GoldenPair)
async def add_golden_pair(
    request: AddGoldenPairRequest,
) -> GoldenPair:
    """Add a new verified question-answer ground truth pair to the dataset."""
    pair_id = f"eval_{request.category}_{uuid.uuid4().hex[:6]}"
    pair_dict = {
        "id": pair_id,
        "category": request.category,
        "query": request.question,
        "expected_answer": request.expected_answer,
        "expected_doc_ids": [],
        "expected_chunk_ids": request.ground_truth_chunk_ids,
        "expected_entities": request.ground_truth_entities,
        "expected_path": None,
        "optimal_strategy": request.expected_route,
        "split": request.split,
        "depends_on": request.depends_on,
    }
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(pair_dict) + "\n")

    return GoldenPair(
        id=pair_id,
        question=request.question,
        category=request.category,
        expected_route=request.expected_route,
        expected_answer=request.expected_answer,
        ground_truth_entities=request.ground_truth_entities,
        ground_truth_chunk_ids=request.ground_truth_chunk_ids,
        split=request.split,
        depends_on=request.depends_on,
        complexity=request.complexity,
    )


@router.post("/golden", response_model=GoldenEvalRunResponse)
async def run_golden_evaluation(
    request: GoldenEvalRunRequest,
) -> GoldenEvalRunResponse:
    """Trigger an automated evaluation run against the golden dataset."""
    started_at = datetime.now(UTC).isoformat()
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    if not GOLDEN_PATH.exists():
        raise HTTPException(status_code=404, detail="Golden questions file not found.")

    split = None if request.split == "all" else request.split
    dataset = GoldenDataset.load_from_jsonl(GOLDEN_PATH)
    if split is not None:
        dataset = dataset.filter_by_split(split)
    if request.sample_size:
        dataset = GoldenDataset(dataset.questions[: request.sample_size])
    if len(dataset) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No golden questions selected for split={request.split!r}.",
        )

    runner = EvaluationRunner()
    report = await runner.run_benchmark(dataset, split=split)

    completed_at = datetime.now(UTC).isoformat()
    return GoldenEvalRunResponse(
        run_id=run_id,
        status="completed",
        split=report.split,
        total_questions=report.total_questions,
        accuracy=round(report.overall_router_accuracy, 4),
        category_scores=report.category_scores,
        category_operational=report.category_operational,
        total_cost_usd=report.total_cost_usd,
        budget_usd=report.budget_usd,
        cache_hit_rate=report.cache_hit_rate,
        started_at=started_at,
        completed_at=completed_at,
    )

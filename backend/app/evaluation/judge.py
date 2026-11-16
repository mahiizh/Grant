"""LLM-judge answer scoring with DeepEval ``GEval``.

Token F1 is lexical: it cannot tell "42 ms" from "42 ms under v1" or recognise a
correct paraphrase. Item 6 makes an LLM judge the primary answer-quality signal
and keeps token F1 as a secondary diagnostic.

The judge is deliberately *not* DeepEval's hosted model. Every call goes through
:class:`app.llm.gateway.ModelGateway`, so the judge shares the run budget, the
on-disk cache, and the retry/backoff policy with the pipeline under test.

DeepEval is imported at module import time because it is a hard dependency of
this module. Its pydantic settings reject an empty ``LITELLM_API_BASE`` (the
repo's ``.env`` ships it blank), so a harmless placeholder is installed just for
the import and removed immediately afterwards. The placeholder must not survive:
LiteLLM reads the same variable, and ``app.core.config`` caches its settings, so
leaving it set would route real judge calls to a localhost proxy that does not
exist. The judge model itself is the local wrapper below and is never contacted
through the placeholder.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.llm.gateway import ModelGateway

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "NO")

_PLACEHOLDER_API_BASE = "http://127.0.0.1:4000"


@contextmanager
def _deepeval_settings_guard() -> Iterator[None]:
    """Satisfy DeepEval's URL validation for the duration of its import only."""
    previous = os.environ.get("LITELLM_API_BASE")
    if not previous:
        os.environ["LITELLM_API_BASE"] = _PLACEHOLDER_API_BASE
    try:
        yield
    finally:
        if not previous:
            os.environ.pop("LITELLM_API_BASE", None)


with _deepeval_settings_guard():
    from deepeval.metrics import GEval  # noqa: E402
    from deepeval.models import DeepEvalBaseLLM  # noqa: E402
    from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

DEFAULT_JUDGE_THRESHOLD = 0.5

CORRECTNESS_CRITERIA = (
    "The actual output answers the input question and is factually consistent with the "
    "expected output. It must include the key facts from the expected output and must not "
    "contradict them. Extra detail is allowed when it is consistent."
)
CORRECTNESS_STEPS = [
    "Identify the key facts asserted by the expected output.",
    "Check whether the actual output states those facts.",
    "Check whether the actual output contradicts any of them.",
    "Score 1 when every key fact is present and none is contradicted, 0.5 when some are "
    "present, and 0 when the answer is missing or contradicts the expected output.",
]

FAITHFULNESS_CRITERIA = (
    "The actual output is supported by the retrieval context. Every factual claim in the "
    "answer must be attributable to the supplied context; unsupported claims make the "
    "answer unfaithful."
)
FAITHFULNESS_STEPS = [
    "Read the retrieval context passages.",
    "For each factual claim in the actual output, find supporting text in the context.",
    "Score 1 when all claims are supported, 0.5 when minor details are unsupported, and 0 "
    "when the answer relies on claims absent from the context.",
]

ABSTENTION_REFERENCE = (
    "The corpus does not contain this information. A correct answer should say that it "
    "cannot be answered from the available documents rather than inventing an answer."
)


@dataclass(frozen=True)
class JudgeVerdict:
    """Per-answer judge output. ``None`` scores mean the judge call failed."""

    correctness_score: float | None
    correctness_pass: bool | None
    faithfulness_score: float | None
    faithfulness_pass: bool | None
    correctness_reason: str = ""
    faithfulness_reason: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "correctness_score": self.correctness_score,
            "correctness_pass": self.correctness_pass,
            "faithfulness_score": self.faithfulness_score,
            "faithfulness_pass": self.faithfulness_pass,
            "correctness_reason": self.correctness_reason,
            "faithfulness_reason": self.faithfulness_reason,
            "error": self.error,
        }


class GatewayJudgeModel(DeepEvalBaseLLM):
    """Adapt :class:`ModelGateway` to the DeepEval judge interface."""

    def __init__(self, gateway: ModelGateway, model_name: str) -> None:
        self.gateway = gateway
        self._model_name = model_name
        self.name = model_name

    def load_model(self, *args: Any, **kwargs: Any) -> GatewayJudgeModel:
        return self

    def get_model_name(self, *args: Any, **kwargs: Any) -> str:
        return self._model_name

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> str:
        response = await self.gateway.complete(prompt=prompt, model=self.name, temperature=0.0)
        return response.content

    def generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> str:
        try:
            return asyncio.run(self.a_generate(prompt, schema=schema, **kwargs))
        except RuntimeError as exc:  # pragma: no cover - sync path is unused in the runner
            raise RuntimeError(
                "GatewayJudgeModel.generate cannot run inside an event loop; use a_generate"
            ) from exc


class AnswerJudge:
    """Score answers for correctness and faithfulness with two GEval metrics."""

    def __init__(
        self,
        gateway: ModelGateway,
        model_name: str | None = None,
        threshold: float = DEFAULT_JUDGE_THRESHOLD,
    ) -> None:
        self.gateway = gateway
        self.model_name = model_name or gateway.default_model
        self.threshold = threshold
        self.model = GatewayJudgeModel(gateway, self.model_name)

    def _correctness_metric(self) -> GEval:
        return GEval(
            name="Answer Correctness",
            criteria=CORRECTNESS_CRITERIA,
            evaluation_steps=CORRECTNESS_STEPS,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            model=self.model,
            threshold=self.threshold,
        )

    def _faithfulness_metric(self) -> GEval:
        return GEval(
            name="Answer Faithfulness",
            criteria=FAITHFULNESS_CRITERIA,
            evaluation_steps=FAITHFULNESS_STEPS,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.RETRIEVAL_CONTEXT,
            ],
            model=self.model,
            threshold=self.threshold,
        )

    async def evaluate(
        self,
        *,
        question: str,
        answer: str,
        expected_answer: str | None,
        context: list[str] | None = None,
    ) -> JudgeVerdict:
        """Judge one answer. Judge failures are recorded, never raised."""
        reference = expected_answer or ABSTENTION_REFERENCE
        test_case = LLMTestCase(
            input=question,
            actual_output=answer,
            expected_output=reference,
            retrieval_context=context or [],
        )

        correctness_metric = self._correctness_metric()
        try:
            score = await correctness_metric.a_measure(test_case, _show_indicator=False)
            correctness_value = round(float(score), 4)
            correctness_score: float | None = correctness_value
            correctness_pass: bool | None = correctness_value >= self.threshold
            correctness_reason = correctness_metric.reason or ""
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the run
            return JudgeVerdict(
                correctness_score=None,
                correctness_pass=None,
                faithfulness_score=None,
                faithfulness_pass=None,
                error=f"correctness: {type(exc).__name__}: {exc}",
            )

        faithfulness_metric = self._faithfulness_metric()
        if not context:
            return JudgeVerdict(
                correctness_score=correctness_score,
                correctness_pass=correctness_pass,
                faithfulness_score=None,
                faithfulness_pass=None,
                correctness_reason=correctness_reason,
                faithfulness_reason="no retrieval context",
            )

        try:
            faith_score = await faithfulness_metric.a_measure(test_case, _show_indicator=False)
            faithfulness_value = round(float(faith_score), 4)
            faithfulness_score: float | None = faithfulness_value
            faithfulness_pass: bool | None = faithfulness_value >= self.threshold
            faithfulness_reason = faithfulness_metric.reason or ""
        except Exception as exc:  # noqa: BLE001
            return JudgeVerdict(
                correctness_score=correctness_score,
                correctness_pass=correctness_pass,
                faithfulness_score=None,
                faithfulness_pass=None,
                correctness_reason=correctness_reason,
                error=f"faithfulness: {type(exc).__name__}: {exc}",
            )

        return JudgeVerdict(
            correctness_score=correctness_score,
            correctness_pass=correctness_pass,
            faithfulness_score=faithfulness_score,
            faithfulness_pass=faithfulness_pass,
            correctness_reason=correctness_reason,
            faithfulness_reason=faithfulness_reason,
        )

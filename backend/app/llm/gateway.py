import asyncio
import os
from dataclasses import dataclass

import litellm

from app.core.config import get_settings


class BudgetExceededError(Exception):
    """Raised when an LLM call exceeds the allocated per-request cost budget."""


MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini/gemini-3.5-flash-lite": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini/gemini-1.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


@dataclass
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: ModelUsage
    cached: bool = False


class ModelGateway:
    """Central gateway for LLM calls enforcing budgets, tracking usage, and routing through LiteLLM."""

    def __init__(
        self,
        default_model: str | None = None,
        max_budget_per_request: float = 0.05,
    ) -> None:
        settings = get_settings()
        self.default_model = default_model or settings.LLM_MODEL
        self.max_budget = max_budget_per_request
        self._total_spent_usd: float = 0.0
        self._total_calls: int = 0

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.1,
        mock_response: str | None = None,
    ) -> ModelResponse:
        """Execute text completion via LiteLLM with real cost and token tracking."""
        settings = get_settings()
        selected_model = model or self.default_model

        # 1. Test / Mock execution path
        if mock_response is not None or (
            settings.APP_ENV == "test" and not settings.GEMINI_API_KEY
        ):
            completion_text = mock_response or "Mock completion based on retrieved context."
            prompt_tokens = max(25, len(prompt.split()))
            completion_tokens = max(35, len(completion_text.split()))
            cost_usd = round((prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003), 6)
            if cost_usd > self.max_budget:
                raise BudgetExceededError(
                    f"Completion cost ${cost_usd:.5f} exceeded max budget ${self.max_budget:.4f}"
                )
            usage = ModelUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost_usd,
            )
            self._total_spent_usd += usage.cost_usd
            self._total_calls += 1
            return ModelResponse(
                content=completion_text,
                model=selected_model,
                usage=usage,
            )

        # 2. Live Provider Path via LiteLLM
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is required in live mode. Please set it in .env"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Set API base or key
        api_key = settings.GEMINI_API_KEY
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        resp = None
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                resp = await litellm.acompletion(
                    model=selected_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=api_key,
                    api_base=settings.LITELLM_API_BASE,
                    timeout=20.0,
                    num_retries=2,
                )
                break
            except Exception as e:
                last_exc = e
                err_str = str(e).lower()
                if (
                    any(
                        x in err_str for x in ("503", "429", "timeout", "unavailable", "rate limit")
                    )
                    and attempt < 4
                ):
                    backoff = 2.5 * (attempt + 1)
                    await asyncio.sleep(backoff)
                    continue
                if isinstance(e, BudgetExceededError):
                    raise
                raise RuntimeError(f"LiteLLM completion failed for {selected_model}: {e}") from e

        if resp is None:
            raise RuntimeError(f"LiteLLM completion failed for {selected_model}: {last_exc}")

        try:
            content = resp.choices[0].message.content or ""
            raw_usage = resp.usage
            prompt_tokens = getattr(raw_usage, "prompt_tokens", 0)
            completion_tokens = getattr(raw_usage, "completion_tokens", 0)
            total_tokens = getattr(raw_usage, "total_tokens", prompt_tokens + completion_tokens)

            try:
                cost = float(litellm.completion_cost(completion_response=resp))
            except Exception:
                # Fallback to standard Flash pricing ($0.075 / 1M prompt, $0.30 / 1M completion)
                cost = (prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003)

            cost_usd = round(cost, 6)
            if cost_usd > self.max_budget:
                raise BudgetExceededError(
                    f"Completion cost ${cost_usd:.5f} exceeded max budget ${self.max_budget:.4f}"
                )

            self._total_spent_usd += cost_usd
            self._total_calls += 1

            return ModelResponse(
                content=content,
                model=selected_model,
                usage=ModelUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                ),
            )
        except Exception as e:
            if isinstance(e, BudgetExceededError):
                raise
            raise RuntimeError(
                f"LiteLLM completion processing failed for {selected_model}: {e}"
            ) from e

    @property
    def total_spent_usd(self) -> float:
        return round(self._total_spent_usd, 6)

    @property
    def total_calls(self) -> int:
        return self._total_calls

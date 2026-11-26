import asyncio
import hashlib
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

# Ensure LiteLLM uses local bundled cost map to prevent remote network timeouts in sandboxed/offline environments
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm

from app.core.config import get_settings


class BudgetExceededError(Exception):
    """Raised when an LLM call exceeds the allocated cost budget."""


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


def _is_retryable(exc: Exception) -> bool:
    """Return True for rate limits, transient 5xx responses, and timeouts."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status == 429 or 500 <= status < 600

    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "429",
            "500",
            "502",
            "503",
            "504",
            "rate limit",
            "timeout",
            "timed out",
            "unavailable",
            "overloaded",
            "temporarily",
        )
    )


def _retry_after_seconds(exc: Exception) -> float | None:
    """Read a provider-supplied retry delay, if one is present."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass

    text = str(exc)
    match = re.search(r"retry in ([\d.]+)s", text, re.IGNORECASE)
    if match is None:
        match = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', text)
    if match is not None:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


class ModelGateway:
    """Central gateway for LLM calls enforcing budgets, tracking usage, and routing through LiteLLM."""

    def __init__(
        self,
        default_model: str | None = None,
        max_budget_per_request: float = 0.05,
        max_budget_per_run: float | None = None,
    ) -> None:
        settings = get_settings()
        self.default_model = default_model or settings.LLM_MODEL
        self.max_budget = max_budget_per_request
        self.max_run_budget = (
            max_budget_per_run
            if max_budget_per_run is not None
            else settings.LLM_MAX_BUDGET_PER_RUN
        )
        self.cache_enabled = settings.LLM_CACHE_ENABLED
        self.cache_dir = Path(settings.LLM_CACHE_DIR)
        self._total_spent_usd: float = 0.0
        self._total_calls: int = 0
        self._cache_hits: int = 0

    def reset_usage(self) -> None:
        """Reset per-run counters so a new benchmark starts from zero cost."""
        self._total_spent_usd = 0.0
        self._total_calls = 0
        self._cache_hits = 0

    def _cache_key(
        self,
        selected_model: str,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        raw = json.dumps(
            {
                "model": selected_model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _read_cache(self, key: str) -> ModelResponse | None:
        if not self.cache_enabled:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stored = data["usage"]
            # A cache hit costs nothing in this run, even though the stored
            # entry remembers what the original completion cost.
            usage = ModelUsage(
                prompt_tokens=stored.get("prompt_tokens", 0),
                completion_tokens=stored.get("completion_tokens", 0),
                total_tokens=stored.get("total_tokens", 0),
                cost_usd=0.0,
            )
            return ModelResponse(
                content=data["content"],
                model=data["model"],
                usage=usage,
                cached=True,
            )
        except (OSError, KeyError, ValueError, TypeError):
            return None

    def _write_cache(self, key: str, response: ModelResponse) -> None:
        if not self.cache_enabled:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "content": response.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "cost_usd": response.usage.cost_usd,
                },
            }
            (self.cache_dir / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            # A read-only or full cache directory must never break generation.
            return

    def _enforce_budgets(self, cost_usd: float) -> None:
        if cost_usd > self.max_budget:
            raise BudgetExceededError(
                f"Completion cost ${cost_usd:.5f} exceeded max budget ${self.max_budget:.4f}"
            )
        if self._total_spent_usd + cost_usd > self.max_run_budget:
            raise BudgetExceededError(
                f"Run budget exceeded: ${self._total_spent_usd + cost_usd:.5f} > "
                f"${self.max_run_budget:.4f}"
            )

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.1,
        mock_response: str | None = None,
    ) -> ModelResponse:
        """Execute text completion via LiteLLM with caching, budgets, and usage tracking."""
        settings = get_settings()
        selected_model = model or self.default_model

        # 1. Test / Mock execution path (never hits the network or the disk cache)
        if mock_response is not None or (
            settings.APP_ENV == "test" and not settings.GEMINI_API_KEY
        ):
            completion_text = mock_response or "Mock completion based on retrieved context."
            prompt_tokens = max(25, len(prompt.split()))
            completion_tokens = max(35, len(completion_text.split()))
            cost_usd = round((prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003), 6)
            self._enforce_budgets(cost_usd)
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

        # 2. On-disk cache keyed by (model, prompt hash)
        cache_key = self._cache_key(selected_model, prompt, system_prompt, max_tokens, temperature)
        cached = self._read_cache(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        # 3. Live provider path via LiteLLM
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is required in live mode. Please set it in .env"
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        api_key = settings.GEMINI_API_KEY
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key

        resp = None
        last_exc: Exception | None = None
        max_attempts = max(1, settings.LITELLM_MAX_ATTEMPTS)
        for attempt in range(max_attempts):
            try:
                resp = await litellm.acompletion(
                    model=selected_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=api_key,
                    api_base=settings.LITELLM_API_BASE,
                    timeout=settings.LITELLM_TIMEOUT_SECONDS,
                    num_retries=1,
                )
                break
            except Exception as e:
                last_exc = e
                if _is_retryable(e) and attempt < max_attempts - 1:
                    # One manual retry with a short bounded backoff. LiteLLM
                    # also gets num_retries=1, so the 45s Ask budget is not
                    # consumed by a long provider retry ladder.
                    delay = min(2.0, 0.25 * (2**attempt))
                    provider_delay = _retry_after_seconds(e)
                    if provider_delay is not None:
                        delay = max(delay, min(provider_delay + 0.5, 5.0))
                    delay += random.uniform(0.0, min(delay * 0.25, 0.5))
                    await asyncio.sleep(delay)
                    continue
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
            self._enforce_budgets(cost_usd)

            self._total_spent_usd += cost_usd
            self._total_calls += 1

            response = ModelResponse(
                content=content,
                model=selected_model,
                usage=ModelUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                ),
            )
            self._write_cache(cache_key, response)
            return response
        except BudgetExceededError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"LiteLLM completion processing failed for {selected_model}: {e}"
            ) from e

    @property
    def total_spent_usd(self) -> float:
        return round(self._total_spent_usd, 6)

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

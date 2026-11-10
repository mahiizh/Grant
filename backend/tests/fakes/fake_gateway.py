import re

from app.llm.gateway import ModelGateway, ModelResponse, ModelUsage


class FakeModelGateway(ModelGateway):
    """Deterministic, network-free model gateway for hermetic tests.

    The default model name starts with ``mock`` so the query condenser uses its
    deterministic heuristic rewrite instead of calling the fake for rewriting.
    Generation is still exercised: the fake synthesizes a cited answer from the
    ``<source_chunk>`` blocks that the orchestrator puts in the prompt.
    """

    def __init__(self) -> None:
        super().__init__(
            default_model="mock-hermetic",
            max_budget_per_request=1.0,
            max_budget_per_run=1.0,
        )
        self.cache_enabled = False

    @staticmethod
    def _synthesize(prompt: str) -> str:
        chunks = re.findall(
            r'<source_chunk id="([^"]+)"[^>]*>\n(.*?)\n</source_chunk>',
            prompt,
            re.DOTALL,
        )
        if chunks:
            first_text = chunks[0][1].strip()
            citations = " ".join(f"[{chunk_id}]" for chunk_id, _ in chunks[:2])
            return f"Based on system documentation, {first_text} {citations}"

        # Condensation fallback: resolve common pronouns with a neutral subject.
        match = re.search(
            r"Follow-up Question:\s*(.*?)\s*Standalone Query:",
            prompt,
            re.DOTALL,
        )
        follow_up = match.group(1).strip() if match else prompt.strip()[:200]
        follow_up = re.sub(r"\bthey\b|\bthem\b", "the engineering team", follow_up)
        follow_up = re.sub(r"\btheir\b", "the engineering team's", follow_up)
        follow_up = re.sub(r"\bit\b|\bthat\b", "the service", follow_up)
        return follow_up

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.1,
        mock_response: str | None = None,
    ) -> ModelResponse:
        selected_model = model or self.default_model
        content = mock_response if mock_response is not None else self._synthesize(prompt)
        prompt_tokens = max(25, len(prompt.split()))
        completion_tokens = max(35, len(content.split()))
        cost_usd = round((prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003), 6)
        usage = ModelUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
        )
        self._total_spent_usd += cost_usd
        self._total_calls += 1
        return ModelResponse(content=content, model=selected_model, usage=usage)

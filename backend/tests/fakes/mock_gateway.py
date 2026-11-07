from dataclasses import dataclass


@dataclass
class FakeModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass
class FakeModelResponse:
    content: str
    model: str
    usage: FakeModelUsage
    cached: bool = False


class FakeModelGateway:
    """Mock gateway for offline tests."""

    def __init__(self, default_model: str = "mock-model") -> None:
        self.default_model = default_model
        self.total_calls = 0

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        mock_response: str | None = None,
    ) -> FakeModelResponse:
        self.total_calls += 1
        content = mock_response or "Mock completion based on retrieved context."
        return FakeModelResponse(
            content=content,
            model=model or self.default_model,
            usage=FakeModelUsage(
                prompt_tokens=20,
                completion_tokens=30,
                total_tokens=50,
                cost_usd=0.0001,
            ),
        )

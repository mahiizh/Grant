from pydantic import BaseModel, Field


class StoreStatus(BaseModel):
    status: str
    latency_ms: float = 0.0
    configured: bool = True


class SettingsResponse(BaseModel):
    shared_scopes: list[str] = Field(default_factory=list)
    canvas_theme: str = "dark"
    stores: dict[str, StoreStatus] = Field(default_factory=dict)


class UpdateSettingsRequest(BaseModel):
    canvas_theme: str | None = None

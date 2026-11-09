from pydantic import BaseModel, Field


class StoreStatus(BaseModel):
    status: str
    latency_ms: float = 0.0
    configured: bool = True


class SettingsResponse(BaseModel):
    acl_scopes: list[str] = Field(default_factory=list)
    default_scope: str = "data-platform"
    default_as_of_date: str = "2026-04-12"
    canvas_theme: str = "dark"
    stores: dict[str, StoreStatus] = Field(default_factory=dict)


class UpdateSettingsRequest(BaseModel):
    default_as_of_date: str | None = None
    canvas_theme: str | None = None

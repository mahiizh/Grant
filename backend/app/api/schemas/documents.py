from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    id: str
    title: str
    file_type: str
    size_kb: int
    chunks: int
    entities_extracted: int
    relations_extracted: int
    tier: int = 1
    ingested_at: str
    target_node_id: str
    tokens: int = 0
    cost_usd: float = 0.0
    extraction_engine: str = "unknown"
    extraction_model: str = ""
    extraction_status: str = "unknown"


class DocumentsResponse(BaseModel):
    documents: list[DocumentRecord]
    total: int


class DocumentUploadResponse(BaseModel):
    document_id: str
    job_id: str
    title: str
    status: str = "queued"
    message: str = "Document ingestion pipeline started"


class DocumentStatusResponse(BaseModel):
    id: str
    job_id: str | None = None
    status: str
    active_step: str
    step_index: int
    total_steps: int = 4
    entities: int = 0
    relations: int = 0
    extraction_engine: str = "unknown"
    extraction_model: str = ""
    extraction_status: str = "unknown"
    error: str | None = None
    ingest_ms: float | None = None


class DocumentImpactResponse(BaseModel):
    document_id: str
    affected_entities: list[str] = Field(default_factory=list)
    affected_relations: list[str] = Field(default_factory=list)
    affected_chunks: list[str] = Field(default_factory=list)
    blast_radius_score: float = 0.0


class StoreDeleteResult(BaseModel):
    """Per-store outcome for a verified document delete."""

    store: str
    remaining: int = 0
    cleared: bool = False
    error: str | None = None


class DocumentDeleteResponse(BaseModel):
    document_id: str
    success: bool
    verified: bool = False
    stores: list[StoreDeleteResult] = Field(default_factory=list)
    # Kept for the existing frontend, which only renders the cleared names.
    stores_cleared: list[str] = Field(default_factory=list)

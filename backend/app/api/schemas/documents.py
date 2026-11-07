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
    valid_from: str
    tokens: int = 0
    cost_usd: float = 0.0



class DocumentsResponse(BaseModel):
    documents: list[DocumentRecord]
    total: int


class DocumentUploadResponse(BaseModel):
    document_id: str
    title: str
    status: str = "ingesting"
    message: str = "Document ingestion pipeline started"


class DocumentStatusResponse(BaseModel):
    id: str
    status: str
    active_step: str
    step_index: int
    total_steps: int = 4
    entities: int = 0
    relations: int = 0


class DocumentImpactResponse(BaseModel):
    document_id: str
    affected_entities: list[str] = Field(default_factory=list)
    affected_relations: list[str] = Field(default_factory=list)
    affected_chunks: list[str] = Field(default_factory=list)
    blast_radius_score: float = 0.0


class DocumentDeleteResponse(BaseModel):
    document_id: str
    success: bool
    stores_cleared: list[str] = Field(default_factory=list)

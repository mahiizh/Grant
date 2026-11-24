from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.acl import ACLScope
from app.domain.provenance import Provenance
from app.domain.temporal import TemporalBounds


class Chunk(BaseModel):
    """Atomic text chunk with embedding coordinates, temporal bounds, and ACL scope."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    doc_id: str
    index: int
    text: str
    tokens: int | None = None
    owner_user_id: str | None = None
    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    temporal: TemporalBounds
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """Source document with versioning, structural metadata, and parsed chunks."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    title: str
    content: str
    chunks: list[Chunk] = Field(default_factory=list)
    owner_user_id: str | None = None
    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    temporal: TemporalBounds
    provenance: Provenance
    version: int = 1
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    """Knowledge graph node representing an extracted real-world entity."""

    model_config = ConfigDict(frozen=True)

    entity_id: str
    name: str
    entity_type: str
    description: str = ""
    canonical_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    temporal: TemporalBounds
    provenance: Provenance
    properties: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    """Knowledge graph edge representing a directed relationship between entities."""

    model_config = ConfigDict(frozen=True)

    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: str = ""
    weight: float = 1.0
    source_chunk_ids: list[str] = Field(default_factory=list)
    acl_scope: ACLScope = Field(default_factory=ACLScope.public)
    temporal: TemporalBounds
    provenance: Provenance


RetrievalMethodType = Literal["dense", "sparse", "graph", "hybrid", "rerank"]


class Evidence(BaseModel):
    """Retrieved evidence passage supporting an answer claim."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    doc_id: str
    text: str
    score: float
    retrieval_method: RetrievalMethodType
    provenance: Provenance
    path: list[str] | None = None


class Answer(BaseModel):
    """Final synthesized answer accompanied by claim-level citations and execution metrics."""

    model_config = ConfigDict(frozen=True)

    query: str
    answer: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    is_abstention: bool = False
    router_strategy: str = "hybrid"
    cost_usd: float = 0.0
    latency_ms: float = 0.0

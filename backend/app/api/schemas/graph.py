from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    # document / entity / query — distinguishes the three visible graph node kinds.
    node_kind: str = "entity"
    aliases: list[str] = Field(default_factory=list)
    ingested_at: str | None = None
    degree: int = 0
    source_kind: str | None = None
    source_kinds: list[str] = Field(default_factory=list)
    description: str | None = None


class GraphLink(BaseModel):
    source: str
    target: str
    label: str = "RELATES_TO"
    tier: int | None = None
    # Aggregated mention/co-occurrence count when the edge carries one.
    count: int | None = None
    ingested_at: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]
    total_nodes: int
    total_links: int


class GraphNeighborsResponse(BaseModel):
    center_node_id: str
    depth: int
    nodes: list[GraphNode]
    links: list[GraphLink]


class GraphPathResponse(BaseModel):
    from_node: str
    to_node: str
    found: bool
    path: list[str] = Field(default_factory=list)
    hops: int = 0
    links: list[GraphLink] = Field(default_factory=list)


class GraphChunkItem(BaseModel):
    """One chunk text from Qdrant for a Postgres entity mention."""

    chunk_id: str
    doc_id: str | None = None
    text: str
    source_kind: str | None = None
    title: str | None = None
    url: str | None = None
    mention_count: int = 0


class GraphEntityChunksResponse(BaseModel):
    entity_id: str
    chunks: list[GraphChunkItem]


class GraphQueryDetailResponse(BaseModel):
    """Answer label and provenance for a Query node in the connected graph."""

    query_id: str
    query: str
    rewritten_query: str | None = None
    answer: str
    source: str
    path: list[str] = Field(default_factory=list)
    top_score: float = 0.0
    answer_policy: str | None = None
    created_at: str | None = None

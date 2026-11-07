from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    pagerank: float = 0.05
    community: int = 0
    cluster: str = "core"
    valid_from: str = "2026-01-01"
    valid_to: str | None = None
    tx_time: str = "2026-01-01T00:00:00Z"
    chunk_hash: str = "sha256:0000"
    degree: int = 1


class GraphLink(BaseModel):
    source: str
    target: str
    label: str = "RELATES_TO"
    tier: int = 1
    valid_from: str = "2026-01-01"
    valid_to: str | None = None
    tx_time: str = "2026-01-01T00:00:00Z"
    chunk_hash: str = "sha256:0000"


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

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    # Analytics that Neo4j does not currently store or compute are ``None``.
    # Clients may compute them from the returned topology.
    pagerank: float | None = None
    community: int | None = None
    cluster: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    tx_time: str | None = None
    chunk_hash: str | None = None
    degree: int = 0


class GraphLink(BaseModel):
    source: str
    target: str
    label: str = "RELATES_TO"
    tier: int | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    tx_time: str | None = None
    chunk_hash: str | None = None


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

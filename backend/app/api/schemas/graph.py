from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    ingested_at: str | None = None
    degree: int = 0
    source_kind: str | None = None
    source_kinds: list[str] = Field(default_factory=list)


class GraphLink(BaseModel):
    source: str
    target: str
    label: str = "RELATES_TO"
    tier: int | None = None
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

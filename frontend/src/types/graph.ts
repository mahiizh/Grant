export type NodeType = "mechanism" | "database" | "person" | "team" | "service";

export interface GraphNode {
  id: string;
  name: string;
  type: NodeType;
  description: string;
  source_kind: string | null;
  source_kinds: string[];
  degree?: number;
  tier: 1 | 2 | 3;
  ingested_at?: string | null;
  status?: "healthy" | "warning" | "active";
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  tier: 1 | 2 | 3;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

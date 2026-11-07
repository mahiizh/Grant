export type NodeType = "mechanism" | "database" | "person" | "team" | "service";

export interface GraphNode {
  id: string;
  name: string;
  type: NodeType;
  description: string;
  cluster?: number;
  degree?: number;
  pageRank?: number;
  lastUpdated?: string;
  status?: "healthy" | "warning" | "active";
  // Bi-temporal & Provenance additions
  valid_from: string; // e.g. "2026-01-15"
  valid_to: string;   // e.g. "9999-12-31"
  tx_time: string;    // transaction time
  tier: 1 | 2 | 3;    // 1: Authoritative, 2: Derived, 3: Inferred
  chunkHash: string;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  tier: 1 | 2 | 3;    // 1: Solid (authoritative), 2: Faint (derived), 3: Dashed (inferred)
  valid_from?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

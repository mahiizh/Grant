export type NodeType =
  | "mechanism"
  | "database"
  | "person"
  | "team"
  | "service"
  | "document"
  | "query"
  | "entity";

export type NodeKind = "document" | "entity" | "query";

export interface GraphNode {
  id: string;
  name: string;
  type: NodeType;
  /** Document / Entity / Query — the three kinds the Step 7 graph displays. */
  node_kind: NodeKind;
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
  /** Aggregated mention / co-occurrence count from the graph edge. */
  count?: number | null;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface GraphChunkText {
  chunk_id: string;
  doc_id: string | null;
  text: string;
  source_kind: string | null;
  title: string | null;
  url: string | null;
  mention_count: number;
}

export interface GraphQueryDetail {
  query_id: string;
  query: string;
  rewritten_query: string | null;
  answer: string;
  source: string;
  path: string[];
  top_score: number;
  answer_policy: string | null;
  created_at: string | null;
}

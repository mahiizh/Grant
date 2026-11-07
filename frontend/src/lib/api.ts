export interface QueryRequest {
  query: string;
  user_roles?: string[];
  user_groups?: string[];
  tenant_id?: string;
  as_of_time?: string | null;
}

export interface EvidenceItem {
  chunk_id: string;
  doc_id: string;
  text: string;
  score: number;
  retrieval_method: string;
  path?: string[] | null;
}

export interface QueryResponse {
  query: string;
  answer: string;
  strategy_used: string;
  is_cached: boolean;
  is_abstention: boolean;
  evidence: EvidenceItem[];
  path?: string[] | null;
  cost_usd: number;
  latency_ms: number;
}

export async function submitQuery(payload: QueryRequest): Promise<QueryResponse> {
  const response = await fetch("/api/v1/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Query failed (${response.status}): ${errorText}`);
  }

  return response.json();
}

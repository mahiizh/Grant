import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import type { GraphChunkText, GraphQueryDetail } from "../../../types/graph";

export function useGraph(options?: {
  limit?: number;
  sourceKind?: string;
  minCooccurrence?: number;
}) {
  const limit = options?.limit ?? 100;
  const source_kind = options?.sourceKind || undefined;
  const min_cooccurrence = options?.minCooccurrence || undefined;

  return useQuery({
    queryKey: ["graph", { limit, source_kind, min_cooccurrence }],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/graph", {
        params: {
          query: { limit, source_kind, min_cooccurrence },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch knowledge graph"));
      return data;
    },
  });
}

/** Entity click: Postgres mentions → ACL-checked Qdrant chunk payloads. */
export function useEntityChunks(entityId: string | null) {
  return useQuery({
    queryKey: ["graph-entity-chunks", entityId],
    queryFn: async (): Promise<GraphChunkText[]> => {
      if (!entityId) return [];
      const { data, error } = await apiClient.GET("/graph/entities/{entity_id}/chunks", {
        params: { path: { entity_id: entityId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch entity chunk texts"));
      return (data?.chunks ?? []) as GraphChunkText[];
    },
    enabled: Boolean(entityId),
  });
}

/** Query click: stored answer, source label and answer path. */
export function useQueryDetail(queryId: string | null) {
  return useQuery({
    queryKey: ["graph-query-detail", queryId],
    queryFn: async (): Promise<GraphQueryDetail | null> => {
      if (!queryId) return null;
      const { data, error } = await apiClient.GET("/graph/queries/{query_id}", {
        params: { path: { query_id: queryId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch query answer"));
      return (data ?? null) as GraphQueryDetail | null;
    },
    enabled: Boolean(queryId),
  });
}

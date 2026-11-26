import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";

export function useGraph(options?: {
  limit?: number;
  sourceKind?: string;
}) {
  const limit = options?.limit ?? 100;
  const source_kind = options?.sourceKind;

  return useQuery({
    queryKey: ["graph", { limit, source_kind }],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/graph", {
        params: {
          query: { limit, source_kind },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch knowledge graph"));
      return data;
    },
  });
}

export function useGraphNeighbors(nodeId: string | null, depth = 1) {
  return useQuery({
    queryKey: ["graph-neighbors", nodeId, depth],
    queryFn: async () => {
      if (!nodeId) return null;
      const { data, error } = await apiClient.GET("/graph/nodes/{node_id}/neighbors", {
        params: {
          path: { node_id: nodeId },
          query: { depth },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch node neighbors"));
      return data;
    },
    enabled: Boolean(nodeId),
  });
}

export function useGraphPath(fromNode: string | null, toNode: string | null) {
  return useQuery({
    queryKey: ["graph-path", fromNode, toNode],
    queryFn: async () => {
      if (!fromNode || !toNode) return null;
      const { data, error } = await apiClient.GET("/graph/path", {
        params: {
          query: { from: fromNode, to: toNode },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to compute graph path"));
      return data;
    },
    enabled: Boolean(fromNode && toNode),
  });
}

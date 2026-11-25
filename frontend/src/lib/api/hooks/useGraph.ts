import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useGraph(options?: {
  scope?: string;
  asOf?: string;
  limit?: number;
  sourceKind?: string;
}) {
  const { aclScope, asOfDate } = useApp();
  const scope = options?.scope ?? aclScope;
  const as_of = options?.asOf ?? asOfDate;
  const limit = options?.limit ?? 100;
  const source_kind = options?.sourceKind;

  return useQuery({
    queryKey: ["graph", { scope, as_of, limit, source_kind }],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/graph", {
        params: {
          query: { scope, as_of, limit, source_kind },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch knowledge graph"));
      return data;
    },
  });
}

export function useGraphNeighbors(nodeId: string | null, depth = 1) {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["graph-neighbors", nodeId, depth, aclScope, asOfDate],
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
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["graph-path", fromNode, toNode, aclScope, asOfDate],
    queryFn: async () => {
      if (!fromNode || !toNode) return null;
      const { data, error } = await apiClient.GET("/graph/path", {
        params: {
          query: {
            from: fromNode,
            to: toNode,
            scope: aclScope,
            as_of: asOfDate,
          },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to compute graph path"));
      return data;
    },
    enabled: Boolean(fromNode && toNode),
  });
}

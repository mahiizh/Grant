import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useTraces(filters?: { route?: string; minLatency?: number; status?: string }) {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["traces", filters, aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/traces", {
        params: {
          query: {
            route: filters?.route && filters.route !== "all" ? filters.route : undefined,
            min_latency: filters?.minLatency,
            status: filters?.status && filters.status !== "all" ? filters.status : undefined,
          },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch traces"));
      return data;
    },
  });
}

export function useTrace(traceId: string | null) {
  return useQuery({
    queryKey: ["trace", traceId],
    queryFn: async () => {
      if (!traceId) return null;
      const { data, error } = await apiClient.GET("/traces/{trace_id}", {
        params: { path: { trace_id: traceId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch trace detail"));
      return data;
    },
    enabled: Boolean(traceId),
  });
}

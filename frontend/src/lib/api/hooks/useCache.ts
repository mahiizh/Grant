import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useCacheStats(window = "24h") {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["cache-stats", window, aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/cache/stats", {
        params: { query: { window } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch cache telemetry"));
      return data;
    },
  });
}

export function useCacheInvalidations() {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["cache-invalidations", aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/cache/invalidations");
      if (error) throw new Error(formatApiError(error, "Failed to fetch cache invalidations"));
      return data;
    },
  });
}

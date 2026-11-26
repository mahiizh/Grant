import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";

export function useOverviewMetrics() {
  return useQuery({
    queryKey: ["overview-metrics"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/metrics/overview");
      if (error) throw new Error(formatApiError(error, "Failed to fetch overview metrics"));
      return data;
    },
  });
}

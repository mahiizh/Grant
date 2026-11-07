import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useGuardrailsMetrics() {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["guardrails-metrics", aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/metrics/guardrails");
      if (error) throw new Error(formatApiError(error, "Failed to fetch guardrail metrics"));
      return data;
    },
  });
}

export function useOverviewMetrics() {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["overview-metrics", aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/metrics/overview");
      if (error) throw new Error(formatApiError(error, "Failed to fetch overview metrics"));
      return data;
    },
  });
}

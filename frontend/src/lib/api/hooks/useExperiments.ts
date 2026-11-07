import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useExperiments() {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["experiments", aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/experiments");
      if (error) throw new Error(formatApiError(error, "Failed to fetch experiments"));
      return data;
    },
  });
}

export function useUpdateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: { experiment_id: string; traffic_split: number }) => {
      const { data, error } = await apiClient.POST("/experiments", {
        body: payload,
      });
      if (error) throw new Error(formatApiError(error, "Failed to update experiment split"));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });
}

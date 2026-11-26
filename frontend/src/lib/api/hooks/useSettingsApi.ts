import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";

export function useSettingsApi() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/settings");
      if (error) throw new Error(formatApiError(error, "Failed to fetch settings"));
      return data;
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: {
      canvas_theme?: string;
    }) => {
      const { data, error } = await apiClient.PATCH("/settings", {
        body: payload,
      });
      if (error) throw new Error(formatApiError(error, "Failed to update settings"));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useStoreHealth() {
  return useQuery({
    queryKey: ["store-health"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/health/ready");
      if (error) throw new Error("Health check failed");
      return data;
    },
    refetchInterval: 10000,
  });
}

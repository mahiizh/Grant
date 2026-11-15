import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useGoldenDataset() {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: ["golden-dataset", aclScope, asOfDate],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/evals/golden/dataset");
      if (error) throw new Error(formatApiError(error, "Failed to fetch golden benchmark set"));
      return data;
    },
  });
}

export function useAddGoldenPair() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: {
      question: string;
      category: string;
      expected_route: string;
      expected_answer: string;
      ground_truth_entities: string[];
      ground_truth_chunk_ids: string[];
      complexity: string;
    }) => {
      const { data, error } = await apiClient.POST("/evals/golden/dataset", {
        body: { ...payload, split: "dev" },
      });
      if (error) throw new Error(formatApiError(error, "Failed to add golden pair"));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["golden-dataset"] });
    },
  });
}

export function useRunGoldenEval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (options?: { dataset_id?: string; sample_size?: number }) => {
      const { data, error } = await apiClient.POST("/evals/golden", {
        body: {
          dataset_id: options?.dataset_id ?? "default",
          sample_size: options?.sample_size,
          split: "test",
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to run golden evaluation"));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["golden-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["overview-metrics"] });
    },
  });
}

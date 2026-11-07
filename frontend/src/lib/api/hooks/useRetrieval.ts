import { useQuery } from "@tanstack/react-query";
import { apiClient, formatApiError } from "../client";
import { useApp } from "../../../context/AppContext";

export function useRetrievalCompare(params: {
  query: string;
  k?: number;
  vectorCutoff?: number;
  crossEncoderCutoff?: number;
}) {
  const { aclScope, asOfDate } = useApp();

  return useQuery({
    queryKey: [
      "retrieval-compare",
      params.query,
      params.k,
      params.vectorCutoff,
      params.crossEncoderCutoff,
      aclScope,
      asOfDate,
    ],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/retrieval/compare", {
        params: {
          query: {
            query: params.query,
            k: params.k ?? 60,
            vector_cutoff: params.vectorCutoff ?? 0.75,
            cross_encoder_cutoff: params.crossEncoderCutoff ?? 0.85,
          },
        },
      });
      if (error) throw new Error(formatApiError(error, "Failed to compare retrieval models"));
      return data;
    },
  });
}

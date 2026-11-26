import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, formatApiError, API_BASE_URL } from "../client";

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/documents");
      if (error) throw new Error(formatApiError(error, "Failed to fetch documents"));
      return data;
    },
  });
}

export function useDocumentStatus(documentId: string | null) {
  return useQuery({
    queryKey: ["document-status", documentId],
    queryFn: async () => {
      if (!documentId) return null;
      const { data, error } = await apiClient.GET("/documents/{document_id}/status", {
        params: { path: { document_id: documentId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch document status"));
      return data;
    },
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1500;
    },
  });
}

export function useDocumentImpact(documentId: string | null) {
  return useQuery({
    queryKey: ["document-impact", documentId],
    queryFn: async () => {
      if (!documentId) return null;
      const { data, error } = await apiClient.GET("/documents/{document_id}/impact", {
        params: { path: { document_id: documentId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to fetch blast radius impact"));
      return data;
    },
    enabled: Boolean(documentId),
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE_URL}/documents`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(formatApiError(errJson, "Failed to upload document"));
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string) => {
      const { data, error } = await apiClient.DELETE("/documents/{document_id}", {
        params: { path: { document_id: documentId } },
      });
      if (error) throw new Error(formatApiError(error, "Failed to delete document"));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["graph"] });
      queryClient.invalidateQueries({ queryKey: ["overview-metrics"] });
    },
  });
}

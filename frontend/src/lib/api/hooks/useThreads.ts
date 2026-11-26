import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL } from "../client";
import { toast } from "sonner";

export interface CitationItem {
  chunk_id: string;
  doc_id: string;
  text: string;
  score: number;
  retrieval_method: string;
  path?: string[] | null;
}

export interface WebSourceItem {
  url?: string | null;
  title?: string | null;
}

export type AnswerSourceKind = "docs" | "web" | "unverified";

export interface PipelineStageItem {
  id: string;
  label: string;
  status: "completed" | "in_progress" | "pending" | "failed" | "running";
  duration_ms?: number;
  detail?: string;
}

export interface MessageGeneration {
  generation_id: string;
  content: string;
  rewritten_query?: string | null;
  route?: string | null;
  cache_status?: string | null;
  latency_ms?: number | null;
  cost_usd?: number | null;
  tokens?: number | null;
  trace_id?: string | null;
  citations: CitationItem[];
  source_kind?: AnswerSourceKind;
  web_sources?: WebSourceItem[];
  query_id?: string | null;
  answer_id?: string | null;
  created_at: string;
}

export interface MessageItem {
  message_id: string;
  thread_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  raw_query?: string | null;
  rewritten_query?: string | null;
  route?: string | null;
  cache_status?: string | null;
  latency_ms?: number | null;
  cost_usd?: number | null;
  tokens?: number | null;
  trace_id?: string | null;
  citations: CitationItem[];
  pipeline_stages: PipelineStageItem[];
  subgraph_nodes: string[];
  feedback?: "up" | "down" | null;
  feedback_note?: string | null;
  generations: MessageGeneration[];
  source_kind?: AnswerSourceKind;
  web_sources?: WebSourceItem[];
  query_id?: string | null;
  answer_id?: string | null;
  created_at: string;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  shared_scope?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview?: string | null;
}

export interface ThreadDetail {
  thread_id: string;
  title: string;
  shared_scope?: string | null;
  created_at: string;
  updated_at: string;
  messages: MessageItem[];
}

export function useThreads() {
  return useQuery<ThreadSummary[]>({
    queryKey: ["threads"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/threads`);
      if (!res.ok) {
        throw new Error("Failed to load conversation threads");
      }
      return res.json();
    },
  });
}

export function useThread(threadId: string | null) {
  return useQuery<ThreadDetail | null>({
    queryKey: ["thread", threadId],
    queryFn: async () => {
      if (!threadId) return null;
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}`);
      if (!res.ok) {
        throw new Error(`Failed to load thread ${threadId}`);
      }
      return res.json();
    },
    enabled: Boolean(threadId),
  });
}

export function useCreateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title?: string }) => {
      const res = await fetch(`${API_BASE_URL}/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Failed to create thread");
      return (await res.json()) as ThreadDetail;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      qc.setQueryData(["thread", data.thread_id], data);
    },
  });
}

export function useUpdateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      threadId,
      ...payload
    }: {
      threadId: string;
      title?: string;
    }) => {
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Failed to update thread");
      return (await res.json()) as ThreadDetail;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      qc.setQueryData(["thread", data.thread_id], data);
    },
  });
}

export function useDeleteThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (threadId: string) => {
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete thread");
      return (await res.json()) as { deleted: boolean; thread_id: string };
    },
    onSuccess: (_, threadId) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      qc.removeQueries({ queryKey: ["thread", threadId] });
      toast.success("Conversation deleted");
    },
  });
}

export function useMessageFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      threadId,
      messageId,
      feedback,
      note,
    }: {
      threadId: string;
      messageId: string;
      feedback: "up" | "down";
      note?: string | null;
    }) => {
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}/messages/${messageId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback, note }),
      });
      if (!res.ok) throw new Error("Failed to record feedback");
      return (await res.json()) as MessageItem;
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["thread", vars.threadId] });
      toast.success(vars.feedback === "up" ? "Feedback recorded: Helpful" : "Feedback recorded: Needs review");
    },
  });
}

export function useAddToGolden() {
  return useMutation({
    mutationFn: async ({
      threadId,
      messageId,
      category = "multi_turn",
      expectedAnswer,
    }: {
      threadId: string;
      messageId: string;
      category?: string;
      expectedAnswer?: string;
    }) => {
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}/messages/${messageId}/golden`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, expected_answer: expectedAnswer }),
      });
      if (!res.ok) throw new Error("Failed to add to golden set");
      return (await res.json()) as { status: string; golden_id: string; file: string };
    },
    onSuccess: (data) => {
      toast.success(`Saved candidate to golden dataset (${data.golden_id})`);
    },
  });
}

export function useRegenerateMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ threadId, messageId }: { threadId: string; messageId: string }) => {
      const res = await fetch(`${API_BASE_URL}/threads/${threadId}/messages/${messageId}/regenerate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to regenerate response");
      return (await res.json()) as MessageItem;
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["thread", vars.threadId] });
      toast.success("New response variation generated");
    },
  });
}

export interface StreamMessageCallbacks {
  onStage?: (stage: PipelineStageItem) => void;
  onRewrite?: (data: { raw_query: string; rewritten_query: string }) => void;
  onToken?: (token: string) => void;
  onCitations?: (citations: CitationItem[]) => void;
  onDone?: (message: MessageItem) => void;
  onError?: (err: Error) => void;
}

export async function streamSendMessage(
  threadId: string,
  payload: {
    content: string;
    retrieval_mode?: string;
    use_cache?: boolean;
    use_rerank?: boolean;
  },
  callbacks: StreamMessageCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/threads/${threadId}/messages?stream=true`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || "Stream request failed");
  }

  if (!res.body) {
    throw new Error("No readable stream response body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const chunk of lines) {
      if (!chunk.trim()) continue;
      const eventMatch = chunk.match(/^event:\s*(\w+)/m);
      const dataMatch = chunk.match(/^data:\s*(.*)$/m);

      if (eventMatch && dataMatch) {
        const eventType = eventMatch[1];
        try {
          const parsed = JSON.parse(dataMatch[1]);
          if (eventType === "stage" && callbacks.onStage) {
            callbacks.onStage(parsed);
          } else if (eventType === "rewrite" && callbacks.onRewrite) {
            callbacks.onRewrite(parsed);
          } else if (eventType === "token" && callbacks.onToken) {
            callbacks.onToken(parsed.token);
          } else if (eventType === "citations" && callbacks.onCitations) {
            callbacks.onCitations(parsed);
          } else if (eventType === "done" && callbacks.onDone) {
            callbacks.onDone(parsed);
          }
        } catch {
          // ignore partial JSON parse errors
        }
      }
    }
  }
}

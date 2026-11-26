import React, { useState, useMemo, useRef, useEffect } from "react";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "../components/ui/resizable";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "../components/ui/tooltip";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { StageStepper, PipelineStage } from "../features/StageStepper";
import { EvidenceInspector, EvidenceChunk, SpanRecord } from "../features/EvidenceInspector";
import { AnswerSourceBadge } from "../features/AnswerSourceBadge";
import { PromptComposer, RetrievalMode } from "../features/PromptComposer";
import { useGraph } from "../lib/api/hooks/useGraph";
import type { GraphLink, GraphNode } from "../types/graph";
import {
  useThreads,
  useThread,
  useCreateThread,
  useUpdateThread,
  useDeleteThread,
  useMessageFeedback,
  useAddToGolden,
  useRegenerateMessage,
  streamSendMessage,
  MessageItem,
  ThreadSummary,
} from "../lib/api/hooks/useThreads";
import {
  Bot,
  User,
  Sparkles,
  Copy,
  ThumbsUp,
  ThumbsDown,
  BookmarkPlus,
  RefreshCw,
  Pencil,
  Search,
  Plus,
  Trash2,
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Check,
  X,
} from "lucide-react";
import { toast } from "sonner";

function groupThreadsByDate(threads: ThreadSummary[]) {
  const today: ThreadSummary[] = [];
  const yesterday: ThreadSummary[] = [];
  const older: ThreadSummary[] = [];

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;

  for (const th of threads) {
    const time = new Date(th.updated_at).getTime();
    if (time >= startOfToday) {
      today.push(th);
    } else if (time >= startOfYesterday) {
      yesterday.push(th);
    } else {
      older.push(th);
    }
  }

  return { today, yesterday, older };
}

export function AskPage() {
  // Thread API Hooks
  const { data: threadsList = [], refetch: refetchThreads } = useThreads();
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const { data: activeThread, refetch: refetchActiveThread } = useThread(activeThreadId);

  const createThreadMutation = useCreateThread();
  const updateThreadMutation = useUpdateThread();
  const deleteThreadMutation = useDeleteThread();
  const feedbackMutation = useMessageFeedback();
  const addToGoldenMutation = useAddToGolden();
  const regenerateMutation = useRegenerateMessage();

  // Selection & UI State
  const [selectedChunkId, setSelectedChunkId] = useState<number | null>(1);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [activeDraftQuery, setActiveDraftQuery] = useState<string>("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchFilter, setSearchFilter] = useState("");
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editingTitleText, setEditingTitleText] = useState("");

  // Version toggles for regenerated messages: messageId -> index
  const [versionIndices, setVersionIndices] = useState<Record<string, number>>({});

  // Negative feedback dialog
  const [feedbackDialogMsgId, setFeedbackDialogMsgId] = useState<string | null>(null);
  const [feedbackNoteText, setFeedbackNoteText] = useState("");

  // Streaming State
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveStreamingMessage, setLiveStreamingMessage] = useState<MessageItem | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-select first thread if none active
  useEffect(() => {
    if (!activeThreadId && threadsList.length > 0) {
      setActiveThreadId(threadsList[0].thread_id);
    }
  }, [threadsList, activeThreadId]);

  // Scroll to bottom on messages change
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [activeThread?.messages, liveStreamingMessage?.content, liveStreamingMessage?.pipeline_stages]);

  // Live Graph API hook for Right Inspector
  const { data: graphResponse } = useGraph();

  const { nodes, links } = useMemo<{ nodes: GraphNode[]; links: GraphLink[] }>(() => {
    if (!graphResponse) return { nodes: [], links: [] };
    return {
      nodes: graphResponse.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        type: n.type as GraphNode["type"],
        description: n.name,
        source_kind: n.source_kind ?? null,
        source_kinds: n.source_kinds ?? [],
        degree: n.degree ?? 0,
        tier: 1,
        ingested_at: n.ingested_at ?? null,
      })),
      links: graphResponse.links.map((l) => ({
        source: l.source,
        target: l.target,
        relation: l.label,
        tier: (l.tier as GraphLink["tier"]) ?? 1,
      })),
    };
  }, [graphResponse]);

  // Active assistant message for Evidence Inspector
  const activeAsstMsg = useMemo(() => {
    if (liveStreamingMessage) return liveStreamingMessage;
    if (!activeThread?.messages) return null;
    if (selectedMessageId) {
      const found = activeThread.messages.find(
        (m) => m.message_id === selectedMessageId && m.role === "assistant"
      );
      if (found) return found;
    }
    const assistantMsgs = activeThread.messages.filter((m) => m.role === "assistant");
    return assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;
  }, [activeThread, selectedMessageId, liveStreamingMessage]);

  // Map active assistant message citations to EvidenceChunk
  const chunks: EvidenceChunk[] = useMemo(() => {
    if (!activeAsstMsg || !activeAsstMsg.citations || activeAsstMsg.citations.length === 0) {
      return [];
    }
    return activeAsstMsg.citations.map((c, idx) => ({
      id: idx + 1,
      file: c.doc_id,
      chunkId: c.chunk_id,
      snippet: c.text,
      highlightedTerm: c.chunk_id,
      score: c.score,
      rrfRank: idx + 1,
      tier: (c.doc_id.includes("rfc") || c.doc_id.includes("dual-write") ? 1 : 2) as 1 | 2 | 3,
      nodeIds: c.path || [c.chunk_id],
    }));
  }, [activeAsstMsg]);

  // Map active assistant message pipeline stages to SpanRecord
  const spans: SpanRecord[] = useMemo(() => {
    if (!activeAsstMsg || !activeAsstMsg.pipeline_stages) return [];
    let elapsed = 0;
    return activeAsstMsg.pipeline_stages.map((st) => {
      const dur = st.duration_ms || 20;
      const s: SpanRecord = {
        name: st.label,
        service:
          st.id === "condense"
            ? "QueryRewriter"
            : st.id === "route"
            ? "LangGraph"
            : st.id === "cache"
            ? "Redis Cache"
            : st.id === "retrieve"
            ? "Qdrant/Neo4j"
            : "ModelGateway",
        startMs: elapsed,
        durationMs: dur,
        status: st.status === "completed" ? "ok" : st.status === "failed" ? "miss" : "hit",
        meta: st.detail || `${dur}ms`,
      };
      elapsed += dur;
      return s;
    });
  }, [activeAsstMsg]);

  // Filter evidence subgraph nodes to only those mentioned in active citations
  const subgraphData = useMemo(() => {
    const citedNodeIds = new Set(chunks.flatMap((c) => c.nodeIds));
    const subNodes = nodes.filter((n) => citedNodeIds.has(n.id));
    const subLinks = links.filter((l) => {
      const s = typeof l.source === "object" ? (l.source as any).id : l.source;
      const t = typeof l.target === "object" ? (l.target as any).id : l.target;
      return citedNodeIds.has(s) && citedNodeIds.has(t);
    });
    return { nodes: subNodes, links: subLinks };
  }, [nodes, links, chunks]);

  // Handle New Chat creation
  const handleCreateNewThread = async () => {
    try {
      const newTh = await createThreadMutation.mutateAsync({
        title: "New Investigation",
      });
      setActiveThreadId(newTh.thread_id);
      setSelectedMessageId(null);
      setActiveDraftQuery("");
      toast.success("New conversation started");
    } catch {
      toast.error("Failed to start new conversation");
    }
  };

  // Handle Delete Thread
  const handleDeleteThread = async (thId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteThreadMutation.mutateAsync(thId);
      if (activeThreadId === thId) {
        const remaining = threadsList.filter((t) => t.thread_id !== thId);
        setActiveThreadId(remaining.length > 0 ? remaining[0].thread_id : null);
      }
    } catch {
      toast.error("Failed to delete thread");
    }
  };

  // Handle Rename Commit
  const handleCommitRename = async (thId: string) => {
    if (!editingTitleText.trim()) {
      setEditingThreadId(null);
      return;
    }
    try {
      await updateThreadMutation.mutateAsync({
        threadId: thId,
        title: editingTitleText.trim(),
      });
      setEditingThreadId(null);
      toast.success("Conversation renamed");
    } catch {
      toast.error("Failed to rename conversation");
    }
  };

  // Stop active streaming
  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setLiveStreamingMessage(null);
    refetchActiveThread();
  };

  // Submit query turn
  const handleQuerySubmit = async (
    query: string,
    mode: RetrievalMode,
    useCache: boolean,
    rerank: boolean
  ) => {
    let currentThreadId = activeThreadId;

    // Create thread if none active
    if (!currentThreadId) {
      const created = await createThreadMutation.mutateAsync({
        title: query.slice(0, 45),
      });
      currentThreadId = created.thread_id;
      setActiveThreadId(currentThreadId);
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setIsStreaming(true);
    setActiveDraftQuery("");

    // Initialize streaming placeholder
    const streamingTempMsg: MessageItem = {
      message_id: "msg-streaming-live",
      thread_id: currentThreadId,
      role: "assistant",
      content: "",
      raw_query: query,
      rewritten_query: query,
      route: mode,
      cache_status: "checking",
      latency_ms: 0,
      cost_usd: 0,
      tokens: 0,
      trace_id: null,
      citations: [],
      pipeline_stages: [
        { id: "condense", label: "Condensing query", status: "running" },
      ],
      subgraph_nodes: [],
      generations: [],
      source_kind: "docs",
      web_sources: [],
      query_id: null,
      answer_id: null,
      created_at: new Date().toISOString(),
    };
    setLiveStreamingMessage(streamingTempMsg);

    try {
      await streamSendMessage(
        currentThreadId,
        {
          content: query,
          retrieval_mode: mode,
          use_cache: useCache,
          use_rerank: rerank,
        },
        {
          onStage: (stage) => {
            setLiveStreamingMessage((prev) => {
              if (!prev) return prev;
              const existingIdx = prev.pipeline_stages.findIndex((s) => s.id === stage.id);
              const updatedStages = [...prev.pipeline_stages];
              if (existingIdx >= 0) {
                updatedStages[existingIdx] = stage;
              } else {
                updatedStages.push(stage);
              }
              return { ...prev, pipeline_stages: updatedStages };
            });
          },
          onRewrite: (data) => {
            setLiveStreamingMessage((prev) =>
              prev
                ? {
                    ...prev,
                    raw_query: data.raw_query,
                    rewritten_query: data.rewritten_query,
                  }
                : prev
            );
          },
          onToken: (tok) => {
            setLiveStreamingMessage((prev) =>
              prev ? { ...prev, content: prev.content + tok } : prev
            );
          },
          onCitations: (cites) => {
            setLiveStreamingMessage((prev) =>
              prev ? { ...prev, citations: cites } : prev
            );
          },
          onDone: (finalMsg) => {
            setIsStreaming(false);
            setLiveStreamingMessage(null);
            setSelectedMessageId(finalMsg.message_id);
            refetchActiveThread();
            refetchThreads();
          },
          onError: (err) => {
            toast.error(err.message || "Failed to stream assistant run");
            setIsStreaming(false);
            setLiveStreamingMessage(null);
          },
        },
        abortController.signal
      );
    } catch (err: any) {
      if (err.name !== "AbortError") {
        toast.error(err.message || "Failed to send message");
      }
    } finally {
      setIsStreaming(false);
      setLiveStreamingMessage(null);
      abortControllerRef.current = null;
    }
  };

  // Feedback upvote
  const handleFeedbackUp = async (msgId: string) => {
    if (!activeThreadId) return;
    try {
      await feedbackMutation.mutateAsync({
        threadId: activeThreadId,
        messageId: msgId,
        feedback: "up",
      });
    } catch {
      toast.error("Failed to record feedback");
    }
  };

  // Feedback downvote submit with note
  const handleSubmitFeedbackDown = async () => {
    if (!activeThreadId || !feedbackDialogMsgId) return;
    try {
      await feedbackMutation.mutateAsync({
        threadId: activeThreadId,
        messageId: feedbackDialogMsgId,
        feedback: "down",
        note: feedbackNoteText.trim() || undefined,
      });
      setFeedbackDialogMsgId(null);
      setFeedbackNoteText("");
    } catch {
      toast.error("Failed to record feedback note");
    }
  };

  // Add to golden dataset
  const handleAddToGolden = async (msgId: string) => {
    if (!activeThreadId) return;
    try {
      await addToGoldenMutation.mutateAsync({
        threadId: activeThreadId,
        messageId: msgId,
        category: "multi_turn",
      });
    } catch {
      toast.error("Failed to add to golden dataset");
    }
  };

  // Regenerate message
  const handleRegenerate = async (msgId: string) => {
    if (!activeThreadId) return;
    try {
      await regenerateMutation.mutateAsync({
        threadId: activeThreadId,
        messageId: msgId,
      });
    } catch {
      toast.error("Failed to regenerate response");
    }
  };

  // Copy message
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Answer copied to clipboard");
  };

  // Render paragraphs with interactive [1], [2], [3] citation pills
  const renderFormattedAnswer = (text: string, currentCitations: any[]) => {
    const paragraphs = text.split("\n\n");
    return paragraphs.map((para, pIdx) => {
      const parts = para.split(/(\[\d+\])/g);
      return (
        <p key={pIdx}>
          {parts.map((part, idx) => {
            const match = part.match(/\[(\d+)\]/);
            if (match) {
              const chunkNum = parseInt(match[1], 10);
              const chunk =
                currentCitations && currentCitations[chunkNum - 1]
                  ? currentCitations[chunkNum - 1]
                  : currentCitations?.[0];
              return (
                <Tooltip key={idx}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedChunkId(chunkNum);
                      }}
                      className="inline-flex items-center justify-center h-4 w-4 rounded-sm bg-amber-500/20 text-amber-300 font-mono text-[10px] font-semibold border border-amber-500/40 hover:bg-amber-500 hover:text-zinc-950 transition-colors mx-0.5 cursor-pointer align-baseline"
                    >
                      {chunkNum}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs bg-zinc-900 border-zinc-800 text-xs p-2.5">
                    <div className="font-mono text-[10px] text-amber-400 mb-1">
                      {chunk?.doc_id || chunk?.file || `Citation #${chunkNum}`} (Sim:{" "}
                      {chunk?.score?.toFixed?.(3) || "0.94"})
                    </div>
                    <div className="text-zinc-300 text-[11px] leading-relaxed line-clamp-3">
                      "{chunk?.text || chunk?.snippet || "Evidence passage supporting claim"}"
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            }
            return <span key={idx}>{part}</span>;
          })}
        </p>
      );
    });
  };

  // Group threads by date
  const filteredThreads = useMemo(() => {
    if (!searchFilter.trim()) return threadsList;
    const lower = searchFilter.toLowerCase();
    return threadsList.filter((t) => t.title.toLowerCase().includes(lower));
  }, [threadsList, searchFilter]);

  const { today, yesterday, older } = useMemo(
    () => groupThreadsByDate(filteredThreads),
    [filteredThreads]
  );

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex-1 h-full overflow-hidden bg-zinc-950 select-none flex">
        {/* ========================================================================= */}
        {/* PANE 1: Collapsible Conversation List (Left) */}
        {/* ========================================================================= */}
        <div
          className={`h-full border-r border-zinc-800/80 bg-zinc-950 flex flex-col transition-all duration-200 shrink-0 ${
            isSidebarOpen ? "w-64 sm:w-72" : "w-12"
          }`}
        >
          {/* Sidebar Header */}
          <div className="p-3 border-b border-zinc-800/80 flex items-center justify-between shrink-0">
            {isSidebarOpen ? (
              <>
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-amber-400" />
                  <span className="text-xs font-semibold tracking-tight text-zinc-100">
                    Investigations
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCreateNewThread}
                    className="h-7 text-[11px] px-2 font-mono border-zinc-800 text-zinc-300 hover:text-amber-300 hover:border-zinc-700 bg-zinc-900/60 cursor-pointer"
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    New
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setIsSidebarOpen(false)}
                    className="h-7 w-7 text-zinc-400 hover:text-zinc-200 cursor-pointer"
                    title="Collapse sidebar"
                  >
                    <PanelLeftClose className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </>
            ) : (
              <Button
                size="icon"
                variant="ghost"
                onClick={() => setIsSidebarOpen(true)}
                className="h-7 w-7 mx-auto text-zinc-400 hover:text-zinc-200 cursor-pointer"
                title="Expand conversations sidebar"
              >
                <PanelLeftOpen className="h-4 w-4 text-amber-400" />
              </Button>
            )}
          </div>

          {/* Collapsed icon view */}
          {!isSidebarOpen && (
            <div className="flex-1 flex flex-col items-center py-3 gap-2">
              <Button
                size="icon"
                variant="outline"
                onClick={handleCreateNewThread}
                className="h-8 w-8 rounded-lg border-zinc-800 bg-zinc-900 hover:text-amber-400 cursor-pointer"
                title="New Chat"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* Expanded Thread List */}
          {isSidebarOpen && (
            <div className="flex-1 flex flex-col min-h-0">
              {/* Search input */}
              <div className="p-2.5 border-b border-zinc-800/60">
                <div className="relative">
                  <Search className="h-3.5 w-3.5 text-zinc-500 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    placeholder="Search threads..."
                    className="w-full bg-zinc-900/60 border border-zinc-800 rounded-md pl-8 pr-2.5 py-1 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-amber-500/50"
                  />
                </div>
              </div>

              {/* Grouped Threads List */}
              <div className="flex-1 overflow-y-auto p-2 space-y-4">
                {[
                  { label: "Today", items: today },
                  { label: "Yesterday", items: yesterday },
                  { label: "Older", items: older },
                ].map(
                  (group) =>
                    group.items.length > 0 && (
                      <div key={group.label} className="space-y-1">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold px-2 py-0.5">
                          {group.label}
                        </div>
                        {group.items.map((th) => {
                          const isActive = th.thread_id === activeThreadId;
                          const isEditing = editingThreadId === th.thread_id;

                          return (
                            <div
                              key={th.thread_id}
                              onClick={() => {
                                setActiveThreadId(th.thread_id);
                                setSelectedMessageId(null);
                              }}
                              className={`group relative p-2 rounded-lg text-xs cursor-pointer border transition-all ${
                                isActive
                                  ? "bg-zinc-900 border-amber-500/40 text-zinc-100 shadow-xs"
                                  : "border-transparent text-zinc-400 hover:bg-zinc-900/50 hover:text-zinc-200"
                              }`}
                            >
                              {isEditing ? (
                                <div className="flex items-center gap-1">
                                  <input
                                    type="text"
                                    value={editingTitleText}
                                    onChange={(e) => setEditingTitleText(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") handleCommitRename(th.thread_id);
                                      if (e.key === "Escape") setEditingThreadId(null);
                                    }}
                                    autoFocus
                                    className="w-full bg-zinc-950 border border-zinc-700 rounded px-1.5 py-0.5 text-xs text-zinc-100 focus:outline-none"
                                  />
                                  <button
                                    onClick={() => handleCommitRename(th.thread_id)}
                                    className="p-1 text-emerald-400 hover:text-emerald-300"
                                  >
                                    <Check className="h-3 w-3" />
                                  </button>
                                  <button
                                    onClick={() => setEditingThreadId(null)}
                                    className="p-1 text-zinc-500 hover:text-zinc-300"
                                  >
                                    <X className="h-3 w-3" />
                                  </button>
                                </div>
                              ) : (
                                <div className="flex items-start justify-between gap-1.5">
                                  <div className="min-w-0 flex-1">
                                    <div className="font-medium truncate text-zinc-200 group-hover:text-amber-300 transition-colors">
                                      {th.title}
                                    </div>
                                    <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                                      <span>{th.message_count} runs</span>
                                    </div>
                                  </div>

                                  {/* Hover actions */}
                                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setEditingThreadId(th.thread_id);
                                        setEditingTitleText(th.title);
                                      }}
                                      className="p-1 text-zinc-500 hover:text-zinc-200 rounded transition-colors"
                                      title="Rename"
                                    >
                                      <Pencil className="h-3 w-3" />
                                    </button>
                                    <button
                                      type="button"
                                      onClick={(e) => handleDeleteThread(th.thread_id, e)}
                                      className="p-1 text-zinc-500 hover:text-red-400 rounded transition-colors"
                                      title="Delete"
                                    >
                                      <Trash2 className="h-3 w-3" />
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )
                )}
              </div>
            </div>
          )}
        </div>

        {/* ========================================================================= */}
        {/* PANE 2 & 3: Center Thread Chat + Right Docked Evidence Inspector */}
        {/* ========================================================================= */}
        <div className="flex-1 h-full overflow-hidden">
          <ResizablePanelGroup orientation="horizontal">
            {/* Center Panel: Thread Messages & Composer */}
            <ResizablePanel defaultSize="58%" minSize="45%" className="flex flex-col h-full overflow-hidden">
              {/* Thread Header Bar */}
              <div className="p-3 border-b border-zinc-800/80 bg-zinc-950 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="h-7 w-7 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0 text-amber-400">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h1 className="text-sm font-semibold tracking-tight text-zinc-100 truncate">
                      {activeThread?.title || "Investigation Workspace"}
                    </h1>
                  </div>
                </div>

                <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/30 text-emerald-400 bg-emerald-500/10 shrink-0">
                  Glass-Box Active
                </Badge>
              </div>

              {/* Messages Thread Scroll Area */}
              <div className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-6">
                {/* Empty State */}
                {(!activeThread?.messages || activeThread.messages.length === 0) &&
                  !liveStreamingMessage && (
                    <div className="py-8 max-w-2xl mx-auto text-center space-y-1.5">
                      <div className="inline-flex items-center justify-center h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 mb-2">
                        <Sparkles className="h-5 w-5" />
                      </div>
                      <h2 className="text-base font-semibold text-zinc-100">
                        Welcome to the Glass-Box RAG Lab
                      </h2>
                      <p className="text-xs text-zinc-400">
                        Every retrieval step, query rewrite, cache hit, and provenance citation is fully transparent.
                        Write your own question below to begin.
                      </p>
                    </div>
                  )}

                {/* Messages Stream */}
                {activeThread?.messages?.map((msg, idx) => {
                  const isUser = msg.role === "user";

                  if (isUser) {
                    return (
                      <div key={msg.message_id} className="flex items-start gap-3">
                          <div className="h-7 w-7 rounded-lg bg-zinc-800 flex items-center justify-center shrink-0 border border-zinc-700">
                            <User className="h-4 w-4 text-zinc-300" />
                          </div>
                          <div className="space-y-1 max-w-2xl">
                            <div className="text-[11px] font-medium text-zinc-400 flex items-center gap-2">
                              <span>User</span>
                              <span className="text-zinc-600 font-mono text-[10px]">
                                {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                              </span>
                            </div>
                            <div className="text-sm font-medium text-zinc-100 bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3 leading-snug">
                              {msg.content}
                            </div>
                          </div>
                      </div>
                    );
                  }

                  // Assistant Turn (Glass-Box Run)
                  const isFocused =
                    selectedMessageId === msg.message_id ||
                    (!selectedMessageId && idx === activeThread.messages.length - 1);

                  // Version switcher logic
                  const hasGenerations = msg.generations && msg.generations.length > 0;
                  const currentVerIdx = versionIndices[msg.message_id] ?? 0;
                  const totalVersions = (msg.generations?.length || 0) + 1;

                  // Rendered version data
                  const displayedContent =
                    currentVerIdx === 0
                      ? msg.content
                      : msg.generations[currentVerIdx - 1]?.content || msg.content;
                  const displayedCitations =
                    currentVerIdx === 0
                      ? msg.citations
                      : msg.generations[currentVerIdx - 1]?.citations || msg.citations;
                  const displayedSourceKind =
                    currentVerIdx === 0
                      ? msg.source_kind
                      : msg.generations[currentVerIdx - 1]?.source_kind || msg.source_kind;
                  const displayedWebSources =
                    currentVerIdx === 0
                      ? msg.web_sources
                      : msg.generations[currentVerIdx - 1]?.web_sources || msg.web_sources;

                  const stages: PipelineStage[] = (msg.pipeline_stages || []).map((s) => ({
                    id: s.id,
                    name: s.label,
                    status: (s.status as any) || "completed",
                    detail: s.detail || "",
                    durationMs: s.duration_ms,
                  }));

                  return (
                    <div
                      key={msg.message_id}
                      onClick={() => setSelectedMessageId(msg.message_id)}
                      className={`flex items-start gap-3 p-3 rounded-2xl transition-all cursor-pointer ${
                        isFocused
                          ? "bg-zinc-900/30 border border-amber-500/30 shadow-[0_0_15px_rgba(245,158,11,0.05)]"
                          : "border border-transparent hover:border-zinc-800/80"
                      }`}
                    >
                      <div className="h-7 w-7 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center shrink-0">
                        <Sparkles className="h-4 w-4" />
                      </div>

                      <div className="space-y-2.5 flex-1 min-w-0">
                        {/* Top: Searched as (condensed query) */}
                        {msg.rewritten_query && msg.rewritten_query !== msg.raw_query && (
                          <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800/80 rounded-md px-2.5 py-1 w-fit">
                            <Sparkles className="h-3 w-3 text-amber-400 shrink-0" />
                            <span className="text-zinc-500">Searched as:</span>
                            <span className="text-zinc-200 italic font-sans font-medium">
                              "{msg.rewritten_query}"
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveDraftQuery(msg.rewritten_query || "");
                              }}
                              className="ml-1 p-0.5 text-zinc-400 hover:text-amber-300 transition-colors"
                              title="Edit rewritten query and re-run"
                            >
                              <Pencil className="h-3 w-3" />
                            </button>
                          </div>
                        )}

                        {/* Stage Stepper: Compact & Expandable */}
                        {stages.length > 0 && (
                          <StageStepper
                            stages={stages}
                            totalLatencyMs={Math.round(msg.latency_ms || 450)}
                            totalCostUsd={msg.cost_usd || 0.0028}
                            isCollapsible={true}
                            defaultExpanded={false}
                          />
                        )}

                        {/* Answer Text Card with Citations */}
                        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4 text-xs sm:text-sm text-zinc-200 leading-relaxed space-y-3">
                          {renderFormattedAnswer(displayedContent, displayedCitations)}

                          {/* Footer Actions & Metadata */}
                          <div className="pt-3 border-t border-zinc-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono select-none">
                            {/* Metadata Strip */}
                            <div className="flex flex-wrap items-center gap-2 text-zinc-400">
                              <AnswerSourceBadge
                                sourceKind={displayedSourceKind}
                                webSources={displayedWebSources}
                              />

                              <Badge variant="outline" className="text-[10px] font-mono border-zinc-800 text-zinc-300 bg-zinc-950 uppercase">
                                {msg.route || "hybrid"}
                              </Badge>

                              <Badge
                                variant="outline"
                                className={`text-[10px] font-mono uppercase ${
                                  msg.cache_status === "hit"
                                    ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                                    : "border-zinc-800 text-zinc-400"
                                }`}
                              >
                                Cache: {msg.cache_status || "miss"}
                              </Badge>

                              <span>{Math.round(msg.latency_ms || 450)}ms</span>
                              <span>·</span>
                              <span>${(msg.cost_usd || 0.0028).toFixed(4)}</span>
                              <span>·</span>
                              <span>{msg.tokens || 310} tokens</span>
                            </div>

                            {/* Message Actions */}
                            <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                              {/* Version arrows if regenerated */}
                              {hasGenerations && (
                                <div className="flex items-center gap-1 mr-2 px-1.5 py-0.5 rounded border border-zinc-800 bg-zinc-950 text-[10px] font-mono text-zinc-400">
                                  <button
                                    onClick={() =>
                                      setVersionIndices((prev) => ({
                                        ...prev,
                                        [msg.message_id]: (currentVerIdx - 1 + totalVersions) % totalVersions,
                                      }))
                                    }
                                    className="p-0.5 hover:text-zinc-200"
                                  >
                                    <ChevronLeft className="h-3 w-3" />
                                  </button>
                                  <span>
                                    {currentVerIdx + 1}/{totalVersions}
                                  </span>
                                  <button
                                    onClick={() =>
                                      setVersionIndices((prev) => ({
                                        ...prev,
                                        [msg.message_id]: (currentVerIdx + 1) % totalVersions,
                                      }))
                                    }
                                    className="p-0.5 hover:text-zinc-200"
                                  >
                                    <ChevronRight className="h-3 w-3" />
                                  </button>
                                </div>
                              )}

                              {/* Copy */}
                              <button
                                onClick={() => handleCopy(displayedContent)}
                                className="p-1.5 text-zinc-400 hover:text-zinc-200 rounded hover:bg-zinc-800/60 transition-colors"
                                title="Copy answer"
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </button>

                              {/* Regenerate */}
                              <button
                                onClick={() => handleRegenerate(msg.message_id)}
                                className="p-1.5 text-zinc-400 hover:text-amber-300 rounded hover:bg-zinc-800/60 transition-colors"
                                title="Regenerate answer variation"
                              >
                                <RefreshCw className="h-3.5 w-3.5" />
                              </button>

                              {/* Feedback Up */}
                              <button
                                onClick={() => handleFeedbackUp(msg.message_id)}
                                className={`p-1.5 rounded hover:bg-zinc-800/60 transition-colors ${
                                  msg.feedback === "up" ? "text-emerald-400" : "text-zinc-400 hover:text-emerald-300"
                                }`}
                                title="Helpful"
                              >
                                <ThumbsUp className="h-3.5 w-3.5" />
                              </button>

                              {/* Feedback Down */}
                              <button
                                onClick={() => {
                                  setFeedbackDialogMsgId(msg.message_id);
                                  setFeedbackNoteText(msg.feedback_note || "");
                                }}
                                className={`p-1.5 rounded hover:bg-zinc-800/60 transition-colors ${
                                  msg.feedback === "down" ? "text-amber-400" : "text-zinc-400 hover:text-amber-300"
                                }`}
                                title="Provide feedback"
                              >
                                <ThumbsDown className="h-3.5 w-3.5" />
                              </button>

                              {/* Add to Golden Set */}
                              <button
                                onClick={() => handleAddToGolden(msg.message_id)}
                                className="p-1.5 text-zinc-400 hover:text-amber-300 rounded hover:bg-zinc-800/60 transition-colors"
                                title="Add to golden evaluation set"
                              >
                                <BookmarkPlus className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Live Streaming Message Display */}
                {liveStreamingMessage && (
                  <div className="flex items-start gap-3 p-3 rounded-2xl bg-zinc-900/30 border border-amber-500/30">
                    <div className="h-7 w-7 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center shrink-0">
                      <Sparkles className="h-4 w-4 animate-spin" />
                    </div>

                    <div className="space-y-2.5 flex-1 min-w-0">
                      {liveStreamingMessage.rewritten_query &&
                        liveStreamingMessage.rewritten_query !== liveStreamingMessage.raw_query && (
                          <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800/80 rounded-md px-2.5 py-1 w-fit">
                            <Sparkles className="h-3 w-3 text-amber-400 shrink-0" />
                            <span className="text-zinc-500">Searched as:</span>
                            <span className="text-zinc-200 italic font-sans font-medium">
                              "{liveStreamingMessage.rewritten_query}"
                            </span>
                          </div>
                        )}

                      <StageStepper
                        stages={liveStreamingMessage.pipeline_stages.map((s) => ({
                          id: s.id,
                          name: s.label,
                          status: s.status as any,
                          detail: s.detail || "",
                        }))}
                        totalLatencyMs={180}
                        totalCostUsd={0.001}
                        isCollapsible={false}
                        defaultExpanded={true}
                      />

                      <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4 text-xs sm:text-sm text-zinc-200 leading-relaxed min-h-[60px]">
                        {liveStreamingMessage.content ? (
                          renderFormattedAnswer(
                            liveStreamingMessage.content,
                            liveStreamingMessage.citations
                          )
                        ) : (
                          <div className="flex items-center gap-2 text-zinc-400 text-xs font-mono">
                            <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
                            <span>Retrieving verified candidates and streaming synthesis...</span>
                          </div>
                        )}
                        <div className="pt-2">
                          <AnswerSourceBadge
                            sourceKind={liveStreamingMessage.source_kind}
                            webSources={liveStreamingMessage.web_sources}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Pinned Composer at Bottom */}
              <div className="p-4 border-t border-zinc-800/80 bg-zinc-950 shrink-0">
                <PromptComposer
                  onSubmitQuery={handleQuerySubmit}
                  isLoading={isStreaming}
                  value={activeDraftQuery}
                  onChangeValue={setActiveDraftQuery}
                  onStopStreaming={handleStopStreaming}
                />
              </div>
            </ResizablePanel>

            {/* Resizable Divider */}
            <ResizableHandle withHandle orientation="horizontal" />

            {/* Right Panel: Docked Evidence Inspector */}
            <ResizablePanel defaultSize="42%" minSize="30%" maxSize="55%">
              <EvidenceInspector
                chunks={chunks}
                selectedChunkId={selectedChunkId}
                onSelectChunk={(id) => setSelectedChunkId(id)}
                subgraphNodes={subgraphData.nodes}
                subgraphLinks={subgraphData.links}
                onSelectNode={(nodeId) => console.log("Selected node from subgraph:", nodeId)}
                spans={spans}
              />
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>

        {/* Feedback Note Dialog */}
        {feedbackDialogMsgId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 max-w-md w-full space-y-3 shadow-2xl">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-100 flex items-center gap-1.5">
                  <ThumbsDown className="h-3.5 w-3.5 text-amber-400" />
                  Flag Answer Quality
                </span>
                <button
                  onClick={() => setFeedbackDialogMsgId(null)}
                  className="text-zinc-500 hover:text-zinc-300 p-1"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>

              <p className="text-xs text-zinc-400">
                Help the evaluation team improve retrieval and synthesis accuracy. Note any hallucinations, missing citations, or incorrect routing.
              </p>

              <textarea
                value={feedbackNoteText}
                onChange={(e) => setFeedbackNoteText(e.target.value)}
                placeholder="e.g. Missed PgBouncer connection limit context; wrong incident commander named."
                rows={3}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-amber-500/50 resize-none"
              />

              <div className="flex justify-end gap-2 pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setFeedbackDialogMsgId(null)}
                  className="h-7 text-xs border-zinc-800 text-zinc-400"
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSubmitFeedbackDown}
                  className="h-7 text-xs bg-amber-500 hover:bg-amber-400 text-zinc-950 font-medium"
                >
                  Submit Feedback
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}

export default AskPage;

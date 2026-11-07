import { useState, useRef, useEffect } from "react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "../components/ui/tooltip";
import { Send, Shield, Calendar, Sparkles, Globe, Square } from "lucide-react";
import { useApp } from "../context/AppContext";

export type RetrievalMode = "auto" | "vector" | "hybrid" | "graph" | "ppr";

export interface GoldenQuery {
  title: string;
  query: string;
  category: string;
}

export const GOLDEN_SUGGESTIONS: GoldenQuery[] = [
  {
    title: "Transactional Outbox & PostgreSQL",
    query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
    category: "Incident Analysis",
  },
  {
    title: "Multi-Hop Dependency Path",
    query: "What databases and services depend on the Qdrant vector index when processing core-banking events?",
    category: "Graph Traversal",
  },
  {
    title: "Bi-Temporal Contract Verification",
    query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
    category: "Bi-Temporal",
  },
  {
    title: "Cache Invalidation Blast Radius",
    query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
    category: "Architecture",
  },
];

export interface PromptComposerProps {
  onSubmitQuery: (query: string, mode: RetrievalMode, useCache: boolean, rerank: boolean) => void;
  isLoading?: boolean;
  value?: string;
  onChangeValue?: (v: string) => void;
  onStopStreaming?: () => void;
  hideSuggestions?: boolean;
}

export function PromptComposer({
  onSubmitQuery,
  isLoading = false,
  value,
  onChangeValue,
  onStopStreaming,
  hideSuggestions = false,
}: PromptComposerProps) {
  const { aclScope, asOfDate } = useApp();
  const [internalQuery, setInternalQuery] = useState("");
  const query = value !== undefined ? value : internalQuery;
  const setQuery = onChangeValue || setInternalQuery;

  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [useCache, setUseCache] = useState(true);
  const [rerank, setRerank] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [query]);

  // Focus textarea when value updates from outside
  useEffect(() => {
    if (value && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [value]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isLoading && onStopStreaming) {
      onStopStreaming();
      return;
    }
    if (!query.trim() || isLoading) return;
    onSubmitQuery(query, mode, useCache, rerank);
    if (!onChangeValue) setInternalQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape" && isLoading && onStopStreaming) {
      e.preventDefault();
      onStopStreaming();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSelectGolden = (g: GoldenQuery) => {
    setQuery(g.query);
    onSubmitQuery(g.query, mode, useCache, rerank);
    if (!onChangeValue) setInternalQuery("");
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-3">
        {/* Suggestion cards when input is empty & not hidden */}
        {!hideSuggestions && query.length === 0 && (
          <div className="space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-amber-400" />
              <span>Golden Benchmark Queries</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {GOLDEN_SUGGESTIONS.map((g) => (
                <button
                  key={g.title}
                  onClick={() => handleSelectGolden(g)}
                  className="p-3 text-left rounded-xl border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-800/60 hover:border-zinc-700 transition-all cursor-pointer group space-y-1"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-zinc-200 group-hover:text-amber-300 transition-colors">
                      {g.title}
                    </span>
                    <Badge variant="outline" className="text-[9px] font-mono text-zinc-400 border-zinc-700">
                      {g.category}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-zinc-400 line-clamp-2">
                    "{g.query}"
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Composer Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 backdrop-blur p-3 space-y-3 shadow-xl">
          {/* Textarea */}
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Ask a follow-up or investigate architecture... (Enter to send, Shift+Enter for newline, Esc to cancel)"
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-xs sm:text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-amber-500/60 resize-none font-sans leading-relaxed"
            />
          </div>

          {/* Controls Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs pt-1 select-none">
            {/* Segmented Mode Control */}
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono text-zinc-500 uppercase">Mode:</span>
              <div className="flex rounded-md border border-zinc-800 bg-zinc-950 p-0.5">
                {(["auto", "vector", "hybrid", "graph", "ppr"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase transition-colors cursor-pointer ${
                      mode === m
                        ? "bg-amber-500 text-zinc-950 font-semibold shadow-xs"
                        : "text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggles & Chips */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Rerank */}
              <label className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rerank}
                  onChange={(e) => setRerank(e.target.checked)}
                  className="rounded border-zinc-700 text-amber-500 focus:ring-0 h-3.5 w-3.5"
                />
                <span className="text-[11px] font-mono">Cross-Encoder</span>
              </label>

              {/* Cache */}
              <label className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useCache}
                  onChange={(e) => setUseCache(e.target.checked)}
                  className="rounded border-zinc-700 text-amber-500 focus:ring-0 h-3.5 w-3.5"
                />
                <span className="text-[11px] font-mono">Semantic Cache</span>
              </label>

              {/* Web Acquisition (Disabled with tooltip) */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1.5 text-zinc-600 opacity-60 cursor-not-allowed">
                    <Globe className="h-3 w-3 text-zinc-600" />
                    <span className="text-[11px] font-mono">Web Acquisition</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="text-[10px] font-mono bg-zinc-900 border-zinc-800 text-zinc-300">
                  Requires external search provider API key (Google SERP / Tavily)
                </TooltipContent>
              </Tooltip>

              {/* Metadata Chips: ACL & As-of */}
              <div className="flex items-center gap-1.5 border-l border-zinc-800 pl-3">
                <Badge variant="outline" className="text-[10px] font-mono border-zinc-800 text-zinc-400 flex items-center gap-1 py-0.5">
                  <Shield className="h-2.5 w-2.5 text-zinc-500" />
                  {aclScope}
                </Badge>

                <Badge variant="outline" className="text-[10px] font-mono border-zinc-800 text-zinc-400 flex items-center gap-1 py-0.5">
                  <Calendar className="h-2.5 w-2.5 text-zinc-500" />
                  {asOfDate}
                </Badge>
              </div>

              {/* Submit or Stop Button */}
              {isLoading ? (
                <Button
                  size="sm"
                  onClick={onStopStreaming}
                  className="bg-amber-600 hover:bg-amber-500 text-zinc-950 font-medium h-7 text-xs px-3 ml-auto cursor-pointer"
                  title="Stop streaming (Esc)"
                >
                  <Square className="h-3 w-3 mr-1 fill-zinc-950" />
                  Stop (Esc)
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => handleSubmit()}
                  disabled={!query.trim()}
                  className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-medium h-7 text-xs px-3 ml-auto cursor-pointer disabled:opacity-40"
                >
                  <Send className="h-3 w-3 mr-1" />
                  Send
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

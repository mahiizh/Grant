import { useState, useRef, useEffect } from "react";
import { Button } from "../components/ui/button";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "../components/ui/tooltip";
import { Send, Globe, Square } from "lucide-react";

export type RetrievalMode = "auto" | "vector" | "hybrid" | "graph";

export interface PromptComposerProps {
  onSubmitQuery: (query: string, mode: RetrievalMode, useCache: boolean, rerank: boolean) => void;
  isLoading?: boolean;
  value?: string;
  onChangeValue?: (v: string) => void;
  onStopStreaming?: () => void;
}

export function PromptComposer({
  onSubmitQuery,
  isLoading = false,
  value,
  onChangeValue,
  onStopStreaming,
}: PromptComposerProps) {
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

  return (
    <TooltipProvider delayDuration={150}>
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
              {(["auto", "vector", "hybrid", "graph"] as const).map((m) => (
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

          {/* Toggles */}
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
    </TooltipProvider>
  );
}

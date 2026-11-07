import { useState } from "react";
import { CheckCircle2, SkipForward, ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "../components/ui/badge";

export interface PipelineStage {
  id: string;
  name: string;
  status: "completed" | "running" | "pending" | "skipped" | "in_progress" | "failed";
  detail: string;
  durationMs?: number;
}

export interface StageStepperProps {
  stages: PipelineStage[];
  totalLatencyMs?: number;
  totalCostUsd?: number;
  isCollapsible?: boolean;
  defaultExpanded?: boolean;
}

export function StageStepper({
  stages,
  totalLatencyMs = 618,
  totalCostUsd = 0.0031,
  isCollapsible = true,
  defaultExpanded = false,
}: StageStepperProps) {
  const isAnyRunning = stages.some((s) => s.status === "running" || s.status === "in_progress");
  const [expanded, setExpanded] = useState(defaultExpanded || isAnyRunning);

  const completedCount = stages.filter((s) => s.status === "completed").length;

  return (
    <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 backdrop-blur select-none overflow-hidden transition-all">
      {/* Header Bar */}
      <div
        onClick={() => isCollapsible && setExpanded(!expanded)}
        className={`p-2.5 flex items-center justify-between text-xs font-mono transition-colors ${
          isCollapsible ? "cursor-pointer hover:bg-zinc-800/40" : ""
        }`}
      >
        <div className="flex items-center gap-2 min-w-0">
          {isAnyRunning ? (
            <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0 animate-ping" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
          )}
          <span className="text-[11px] text-zinc-300 font-semibold tracking-wide">
            Pipeline Execution
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">
            ({completedCount}/{stages.length} stages)
          </span>

          {!expanded && (
            <span className="hidden sm:inline-block text-[10px] text-zinc-400 truncate max-w-xs font-mono">
              · {stages.map((s) => s.name).join(" → ")}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/30 text-emerald-400 bg-emerald-500/10 py-0">
            {totalLatencyMs}ms
          </Badge>
          <Badge variant="outline" className="text-[10px] font-mono border-amber-500/30 text-amber-400 bg-amber-500/10 py-0">
            ${totalCostUsd.toFixed(4)}
          </Badge>

          {isCollapsible && (
            <button
              type="button"
              className="p-0.5 text-zinc-400 hover:text-zinc-200 transition-colors"
              aria-label={expanded ? "Collapse stages" : "Expand stages"}
            >
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
      </div>

      {/* Expanded Stages Body */}
      {expanded && (
        <div className="p-3 pt-0 border-t border-zinc-800/60 mt-1">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-2 text-xs">
            {stages.map((st, idx) => {
              const isCompleted = st.status === "completed";
              const isRunning = st.status === "running" || st.status === "in_progress";
              const isSkipped = st.status === "skipped";

              return (
                <div key={st.id} className="flex items-center gap-1.5 shrink-0">
                  <div
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-mono transition-all ${
                      isCompleted
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                        : isRunning
                        ? "border-amber-500/50 bg-amber-500/15 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.3)] animate-pulse"
                        : isSkipped
                        ? "border-zinc-800 bg-zinc-900/40 text-zinc-600 line-through"
                        : "border-zinc-800 bg-zinc-900/20 text-zinc-500"
                    }`}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                    ) : isRunning ? (
                      <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0 animate-ping" />
                    ) : isSkipped ? (
                      <SkipForward className="h-3 w-3 text-zinc-600 shrink-0" />
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-zinc-700 shrink-0" />
                    )}

                    <span className="font-medium text-zinc-200">{st.name}</span>
                    {st.detail && (
                      <span className="text-[10px] text-zinc-400 opacity-90">({st.detail})</span>
                    )}
                  </div>

                  {idx < stages.length - 1 && (
                    <span className="text-zinc-600 text-xs font-mono">→</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

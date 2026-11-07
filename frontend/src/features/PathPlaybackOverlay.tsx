import { useState, useEffect } from "react";
import { Sparkles, ChevronLeft, ChevronRight, Play, Pause, RotateCcw, X } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { EnrichedNode } from "../hooks/useGraphAnalytics";

export interface PathPlaybackOverlayProps {
  path: string[];
  nodes: EnrichedNode[];
  onSelectHop: (nodeId: string, index: number) => void;
  onDismiss: () => void;
}

export function PathPlaybackOverlay({
  path,
  nodes,
  onSelectHop,
  onDismiss,
}: PathPlaybackOverlayProps) {
  const [currentHopIndex, setCurrentHopIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Automated playback
  useEffect(() => {
    if (!isPlaying) return;

    const timer = setInterval(() => {
      setCurrentHopIndex((prev) => {
        if (prev >= path.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        const next = prev + 1;
        onSelectHop(path[next], next);
        return next;
      });
    }, 1200);

    return () => clearInterval(timer);
  }, [isPlaying, path, onSelectHop]);

  const handleHopClick = (index: number) => {
    setCurrentHopIndex(index);
    onSelectHop(path[index], index);
  };

  const handlePrev = () => {
    if (currentHopIndex > 0) {
      const prev = currentHopIndex - 1;
      setCurrentHopIndex(prev);
      onSelectHop(path[prev], prev);
    }
  };

  const handleNext = () => {
    if (currentHopIndex < path.length - 1) {
      const next = currentHopIndex + 1;
      setCurrentHopIndex(next);
      onSelectHop(path[next], next);
    }
  };

  const handleReplay = () => {
    setCurrentHopIndex(0);
    onSelectHop(path[0], 0);
    setIsPlaying(true);
  };

  return (
    <div className="absolute top-4 left-4 right-4 sm:left-auto sm:right-4 z-10 p-2.5 rounded-xl border border-amber-500/30 bg-zinc-950/85 backdrop-blur-md shadow-2xl flex flex-wrap items-center justify-between gap-3 text-xs select-none">
      <div className="flex items-center gap-2 overflow-x-auto max-w-full">
        <span className="font-semibold text-amber-400 flex items-center gap-1 shrink-0 font-mono text-[11px]">
          <Sparkles className="h-3.5 w-3.5 text-amber-400 animate-pulse" />
          Reasoning Path ({currentHopIndex + 1}/{path.length}):
        </span>

        <div className="flex items-center gap-1">
          {path.map((nodeId, idx) => {
            const node = nodes.find((n) => n.id === nodeId);
            const isCurrent = idx === currentHopIndex;
            const isPast = idx < currentHopIndex;

            return (
              <div key={nodeId} className="flex items-center gap-1 shrink-0">
                <Badge
                  variant="outline"
                  onClick={() => handleHopClick(idx)}
                  className={`text-[10px] font-mono cursor-pointer transition-all ${
                    isCurrent
                      ? "border-amber-400 bg-amber-500/20 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.5)]"
                      : isPast
                      ? "border-amber-500/40 bg-zinc-900/60 text-amber-400/80"
                      : "border-zinc-800 bg-zinc-900/30 text-zinc-500"
                  }`}
                >
                  {node?.name || nodeId}
                </Badge>
                {idx < path.length - 1 && (
                  <span className={`text-[11px] ${idx < currentHopIndex ? "text-amber-500" : "text-zinc-600"}`}>
                    →
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Playback Controls */}
      <div className="flex items-center gap-1.5 shrink-0 ml-auto border-l border-zinc-800/80 pl-2.5">
        <button
          onClick={handlePrev}
          disabled={currentHopIndex === 0}
          className="p-1 rounded text-zinc-400 hover:text-zinc-100 disabled:opacity-30 disabled:pointer-events-none hover:bg-zinc-800 transition-colors cursor-pointer"
          title="Previous Hop"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={() => setIsPlaying(!isPlaying)}
          className="p-1 rounded text-amber-400 hover:text-amber-300 hover:bg-zinc-800 transition-colors cursor-pointer"
          title={isPlaying ? "Pause Playback" : "Auto-Step Path"}
        >
          {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </button>

        <button
          onClick={handleNext}
          disabled={currentHopIndex >= path.length - 1}
          className="p-1 rounded text-zinc-400 hover:text-zinc-100 disabled:opacity-30 disabled:pointer-events-none hover:bg-zinc-800 transition-colors cursor-pointer"
          title="Next Hop"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={handleReplay}
          className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
          title="Replay Path Sequence"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={onDismiss}
          className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors cursor-pointer"
          title="Dismiss Path"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

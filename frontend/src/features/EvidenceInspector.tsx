import { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { GraphCanvas2D } from "./GraphCanvas2D";
import { GraphLink, GraphNode } from "../types/graph";
import {
  FileText,
  Network,
  Activity,
  ExternalLink,
  Sparkles,
} from "lucide-react";

export interface EvidenceChunk {
  id: number;
  file: string;
  chunkId: string;
  snippet: string;
  highlightedTerm: string;
  score: number;
  rrfRank: number;
  tier: 1 | 2 | 3;
  nodeIds: string[];
}

export interface SpanRecord {
  name: string;
  service: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "miss" | "hit";
  meta: string;
}

export interface EvidenceInspectorProps {
  chunks: EvidenceChunk[];
  selectedChunkId: number | null;
  onSelectChunk: (id: number) => void;
  subgraphNodes: GraphNode[];
  subgraphLinks: GraphLink[];
  onSelectNode: (nodeId: string) => void;
  spans: SpanRecord[];
}

export function EvidenceInspector({
  chunks,
  selectedChunkId,
  onSelectChunk,
  subgraphNodes,
  subgraphLinks,
  onSelectNode,
  spans,
}: EvidenceInspectorProps) {
  const [activeTab, setActiveTab] = useState("citations");

  const totalTraceDuration = Math.max(
    ...spans.map((s) => s.startMs + s.durationMs),
    500
  );

  return (
    <div className="h-full flex flex-col bg-zinc-950 border-l border-zinc-800/80 text-xs select-none overflow-hidden">
      {/* Header and Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col min-h-0">
        <div className="p-3 border-b border-zinc-800/80 bg-zinc-900/50 shrink-0">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 font-semibold text-zinc-200">
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
              <span>Grounding Evidence & Inspector</span>
            </div>
            <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">
              {chunks.length} Grounded Chunks
            </Badge>
          </div>

          <TabsList className="w-full bg-zinc-950 border border-zinc-800 h-8 p-0.5 grid grid-cols-3">
            <TabsTrigger value="citations" className="text-[11px] font-mono h-7">
              <FileText className="h-3 w-3 mr-1" />
              Citations ({chunks.length})
            </TabsTrigger>
            <TabsTrigger value="subgraph" className="text-[11px] font-mono h-7">
              <Network className="h-3 w-3 mr-1" />
              Evidence Graph
            </TabsTrigger>
            <TabsTrigger value="trace" className="text-[11px] font-mono h-7">
              <Activity className="h-3 w-3 mr-1" />
              Mini Trace
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Main Content Area */}
        {/* Tab 1: Citations / Chunks */}
        <TabsContent value="citations" className="flex-1 overflow-y-auto p-3 min-h-0 m-0 space-y-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold flex items-center justify-between">
            <span>Grounding Sources</span>
            <span>RRF Blended</span>
          </div>

          {chunks.map((chunk) => {
            const isSelected = selectedChunkId === chunk.id;

            return (
              <div
                key={chunk.id}
                onClick={() => onSelectChunk(chunk.id)}
                className={`p-3 rounded-xl border transition-all cursor-pointer space-y-2 ${
                  isSelected
                    ? "border-amber-500/50 bg-amber-500/10 shadow-[0_0_12px_rgba(245,158,11,0.15)]"
                    : "border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-800/50 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="h-4 w-4 rounded bg-amber-500/20 text-amber-400 font-mono text-[10px] font-semibold flex items-center justify-center border border-amber-500/40 shrink-0">
                      {chunk.id}
                    </span>
                    <span className="font-mono text-[11px] text-zinc-200 font-medium truncate">
                      {chunk.file}
                    </span>
                  </div>

                  <Badge
                    variant="outline"
                    className={`text-[9px] font-mono shrink-0 ${
                      chunk.tier === 1
                        ? "border-sky-400/40 text-sky-400 bg-sky-400/10"
                        : chunk.tier === 2
                        ? "border-emerald-400/40 text-emerald-400 bg-emerald-400/10"
                        : "border-amber-400/40 text-amber-400 bg-amber-400/10"
                    }`}
                  >
                    Tier {chunk.tier}
                  </Badge>
                </div>

                {/* Chunk text snippet with highlighted term */}
                <div className="text-zinc-300 text-xs leading-relaxed font-sans bg-zinc-950/60 p-2.5 rounded-lg border border-zinc-800/60">
                  "{chunk.snippet.split(chunk.highlightedTerm).map((part, i, arr) => (
                    <span key={i}>
                      {part}
                      {i < arr.length - 1 && (
                        <mark className="bg-amber-400/20 text-amber-300 px-1 py-0.5 rounded font-medium">
                          {chunk.highlightedTerm}
                        </mark>
                      )}
                    </span>
                  ))}"
                </div>

                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 pt-1 border-t border-zinc-800/50">
                  <span className="text-emerald-400 font-medium">
                    Sim: {chunk.score.toFixed(3)}
                  </span>
                  <span>RRF Rank: #{chunk.rrfRank}</span>
                  <span className="text-zinc-400 flex items-center gap-1 hover:text-zinc-200">
                    <span>{chunk.chunkId}</span>
                    <ExternalLink className="h-2.5 w-2.5" />
                  </span>
                </div>
              </div>
            );
          })}
        </TabsContent>

        {/* Tab 2: Evidence Subgraph */}
        <TabsContent value="subgraph" className="flex-1 overflow-y-auto p-3 min-h-0 m-0 flex flex-col space-y-2">
          <div className="text-[10px] font-mono text-zinc-400 flex items-center justify-between">
            <span>Isolated Subgraph: {subgraphNodes.length} nodes · {subgraphLinks.length} links</span>
            <span className="text-amber-400">Path Illuminated</span>
          </div>
          <div className="flex-1 min-h-[320px] rounded-xl border border-zinc-800/80 overflow-hidden relative bg-[#09090b]">
            <GraphCanvas2D
              nodes={subgraphNodes}
              links={subgraphLinks}
              colorBy="type"
              selectedNodeId={null}
              activePath={subgraphNodes.map((n) => n.id)}
              highlightedPathNodes={new Set(subgraphNodes.map((n) => n.id))}
              onSelectNode={(node) => onSelectNode(node.id)}
              zoomToTrigger={1}
            />
          </div>
          <div className="p-2 rounded-lg bg-zinc-900/40 border border-zinc-800 text-[11px] text-zinc-400 font-mono">
            Nodes referenced in citations: {subgraphNodes.map((n) => n.name).join(" → ")}
          </div>
        </TabsContent>

        {/* Tab 3: Mini Trace Waterfall */}
        <TabsContent value="trace" className="flex-1 overflow-y-auto p-3 min-h-0 m-0 space-y-3">
          <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
            <span className="uppercase tracking-wider font-semibold">Span Name</span>
            <span>{totalTraceDuration}ms Timeline</span>
          </div>

          <div className="space-y-2">
            {spans.map((sp, idx) => {
              const leftPercent = (sp.startMs / totalTraceDuration) * 100;
              const widthPercent = Math.max((sp.durationMs / totalTraceDuration) * 100, 3);

              return (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg border border-zinc-800/80 bg-zinc-900/40 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span className="font-semibold text-zinc-200">{sp.name}</span>
                      <span className="text-[10px] text-zinc-500">({sp.service})</span>
                    </div>
                    <span className="text-amber-400 font-mono tabular-nums text-[11px]">
                      {sp.durationMs}ms
                    </span>
                  </div>

                  {/* Gantt Bar */}
                  <div className="w-full bg-zinc-950 rounded-full h-2 relative overflow-hidden">
                    <div
                      className="absolute h-full rounded-full bg-amber-400/80"
                      style={{
                        left: `${leftPercent}%`,
                        width: `${widthPercent}%`,
                      }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
                    <span>Meta: {sp.meta}</span>
                    <span>offset +{sp.startMs}ms</span>
                  </div>
                </div>
              );
            })}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

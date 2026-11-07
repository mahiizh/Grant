import { useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { EnrichedNode } from "../hooks/useGraphAnalytics";
import { GraphLink } from "../types/graph";
import { Route, Sparkles, ExternalLink, ArrowRight, ShieldCheck } from "lucide-react";

export interface NodeDetailPanelProps {
  node: EnrichedNode | null;
  isOpen: boolean;
  onClose: () => void;
  allNodes: EnrichedNode[];
  links: GraphLink[];
  onSelectNode: (nodeId: string) => void;
  onFindPath: (sourceId: string, targetId: string) => void;
}

export function NodeDetailPanel({
  node,
  isOpen,
  onClose,
  allNodes,
  links,
  onSelectNode,
  onFindPath,
}: NodeDetailPanelProps) {
  const [selectedTarget, setSelectedTarget] = useState<string>("");

  if (!node) return null;

  // Find incoming and outgoing neighbors
  const outgoing = links.filter((l) => l.source === node.id || (typeof l.source === "object" && (l.source as any).id === node.id));
  const incoming = links.filter((l) => l.target === node.id || (typeof l.target === "object" && (l.target as any).id === node.id));

  const typeVariants: Record<string, "graph" | "vector" | "warning" | "success" | "secondary"> = {
    mechanism: "warning",
    database: "vector",
    person: "graph",
    team: "graph",
    service: "success",
  };

  const handleStartPathFinding = () => {
    if (!selectedTarget || selectedTarget === node.id) return;
    onFindPath(node.id, selectedTarget);
  };

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="sm:max-w-md w-full overflow-y-auto">
        <SheetHeader className="pb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={typeVariants[node.type] || "secondary"} className="uppercase font-mono text-[10px]">
              {node.type}
            </Badge>
            <Badge variant="outline" className="text-[10px] text-zinc-400">
              {node.clusterName}
            </Badge>
            {node.status && (
              <Badge
                variant={node.status === "healthy" ? "success" : node.status === "warning" ? "warning" : "default"}
                className="text-[10px]"
              >
                {node.status}
              </Badge>
            )}
          </div>
          <SheetTitle className="text-xl font-bold text-zinc-100 mt-2 font-sans tracking-tight">
            {node.name}
          </SheetTitle>
          <SheetDescription className="text-xs text-zinc-400 leading-relaxed">
            {node.description}
          </SheetDescription>
        </SheetHeader>

        {/* Analytics & Metrics */}
        <div className="py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
              <span className="text-[11px] text-zinc-400 block pb-1">PageRank Centrality</span>
              <span className="text-lg font-mono font-bold text-sky-400">
                {node.pageRank.toFixed(4)}
              </span>
              <div className="w-full bg-zinc-800 h-1.5 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-sky-400 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(node.pageRank * 800, 100)}%` }}
                />
              </div>
            </div>

            <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
              <span className="text-[11px] text-zinc-400 block pb-1">Degrees (Total / In / Out)</span>
              <span className="text-lg font-mono font-bold text-purple-400">
                {node.degree}
              </span>
              <span className="text-[11px] text-zinc-500 block mt-1 font-mono">
                &darr; {node.inDegree} in • &uarr; {node.outDegree} out
              </span>
            </div>
          </div>

          {/* Interactive Path Finding */}
          <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-950/20 space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-purple-300">
              <Route className="h-4 w-4" /> Find Shortest Reasoning Path
            </div>
            <p className="text-[11px] text-zinc-400">
              Compute Graphology bidirectional shortest path from <strong className="text-zinc-200">{node.name}</strong> to any node with glowing directional particle beams.
            </p>

            <div className="flex gap-2">
              <select
                value={selectedTarget}
                onChange={(e) => setSelectedTarget(e.target.value)}
                className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-purple-400 font-sans"
              >
                <option value="">Select destination entity...</option>
                {allNodes
                  .filter((n) => n.id !== node.id)
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name} ({n.type})
                    </option>
                  ))}
              </select>

              <Button
                size="sm"
                variant="default"
                disabled={!selectedTarget}
                onClick={handleStartPathFinding}
                className="bg-purple-600 hover:bg-purple-500 text-white gap-1 text-xs px-3"
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>Trace</span>
              </Button>
            </div>
          </div>

          {/* Connected Edges & Relationships */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-300">
              <span>Connected Relationships</span>
              <span className="text-zinc-500 font-mono text-[11px]">{outgoing.length + incoming.length} edges</span>
            </div>

            <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {outgoing.map((l, i) => {
                const targetId = typeof l.target === "object" ? (l.target as any).id : l.target;
                const targetNode = allNodes.find((n) => n.id === targetId);

                return (
                  <div
                    key={`out-${i}`}
                    onClick={() => onSelectNode(targetId)}
                    className="p-2.5 rounded-lg border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-800/80 transition-colors flex items-center justify-between cursor-pointer group text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-[10px] font-mono font-bold text-amber-400 uppercase tracking-wider">
                        {l.relation}
                      </span>
                      <ArrowRight className="h-3 w-3 text-zinc-500 shrink-0" />
                      <span className="text-zinc-200 group-hover:text-white truncate font-medium">
                        {targetNode?.name || targetId}
                      </span>
                    </div>
                    <ExternalLink className="h-3 w-3 text-zinc-500 group-hover:text-zinc-300 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                );
              })}

              {incoming.map((l, i) => {
                const sourceId = typeof l.source === "object" ? (l.source as any).id : l.source;
                const sourceNode = allNodes.find((n) => n.id === sourceId);

                return (
                  <div
                    key={`in-${i}`}
                    onClick={() => onSelectNode(sourceId)}
                    className="p-2.5 rounded-lg border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-800/80 transition-colors flex items-center justify-between cursor-pointer group text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-zinc-400 group-hover:text-white truncate font-medium">
                        {sourceNode?.name || sourceId}
                      </span>
                      <ArrowRight className="h-3 w-3 text-zinc-500 shrink-0" />
                      <span className="text-[10px] font-mono font-bold text-purple-400 uppercase tracking-wider">
                        {l.relation}
                      </span>
                    </div>
                    <ExternalLink className="h-3 w-3 text-zinc-500 group-hover:text-zinc-300 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Provenance and Temporal Info */}
          <div className="p-3 rounded-lg border border-zinc-800/60 bg-zinc-950/40 text-[11px] text-zinc-400 space-y-1">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-zinc-300">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" /> Bi-Temporal Provenance
              </span>
              <span className="font-mono text-zinc-500">Tier 1 Document</span>
            </div>
            <div className="flex items-center justify-between text-zinc-500 font-mono text-[10px] pt-1">
              <span>Valid From: {node.lastUpdated || "2026-04-12"}</span>
              <span>Valid To: Ongoing</span>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

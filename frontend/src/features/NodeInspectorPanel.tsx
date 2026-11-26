import { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { GraphLink, GraphNode } from "../types/graph";
import {
  Sparkles,
  ArrowRight,
  Layers,
  Copy,
  Check,
  X,
  Compass,
} from "lucide-react";
import { toast } from "sonner";

export interface NodeInspectorPanelProps {
  node: GraphNode | null;
  nodes: GraphNode[];
  links: GraphLink[];
  onSelectNode: (nodeId: string) => void;
  onFindPath: (sourceId: string, targetId: string) => void;
  onClose?: () => void;
}

export function NodeInspectorPanel({
  node,
  nodes,
  links,
  onSelectNode,
  onFindPath,
  onClose,
}: NodeInspectorPanelProps) {
  const [selectedTarget, setSelectedTarget] = useState("");
  const [copiedCypher, setCopiedCypher] = useState(false);

  if (!node) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center text-zinc-500 select-none bg-zinc-950">
        <Compass className="h-10 w-10 text-zinc-700 mb-3 animate-pulse" />
        <h3 className="text-sm font-medium text-zinc-300">No Node Selected</h3>
        <p className="text-xs text-zinc-500 mt-1 max-w-xs leading-relaxed">
          Select a node from the canvas, table, or search to inspect its neighborhood and provenance.
        </p>
      </div>
    );
  }

  // Incoming and outgoing links
  const outgoing = links.filter(
    (l) => l.source === node.id || (typeof l.source === "object" && (l.source as any).id === node.id)
  );
  const incoming = links.filter(
    (l) => l.target === node.id || (typeof l.target === "object" && (l.target as any).id === node.id)
  );

  const typeVariants: Record<string, "graph" | "vector" | "warning" | "success" | "secondary"> = {
    mechanism: "warning",
    database: "vector",
    person: "graph",
    team: "graph",
    service: "success",
  };

  const handleCopyCypher = () => {
    const cypher = `MATCH (n {id: "${node.id}"})-[r]-(m)
RETURN n, r, m LIMIT 50;`;
    navigator.clipboard.writeText(cypher);
    setCopiedCypher(true);
    toast.success("Copied Cypher query to clipboard");
    setTimeout(() => setCopiedCypher(false), 2000);
  };

  return (
    <div className="h-full flex flex-col bg-zinc-950 border-l border-zinc-800/80 select-none overflow-hidden text-xs">
      {/* Header */}
      <div className="p-4 border-b border-zinc-800/80 bg-zinc-900/40 flex items-start justify-between gap-3 shrink-0">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-sm font-semibold text-zinc-100 truncate tracking-tight">
              {node.name}
            </h2>
            <Badge variant={typeVariants[node.type] || "secondary"} className="text-[10px] uppercase font-mono">
              {node.type}
            </Badge>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-zinc-400 font-mono">
            <span className="truncate">{node.source_kind || "unknown source"}</span>
            <span>·</span>
            <span className="tabular-nums">Tier {node.tier}</span>
          </div>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer shrink-0"
            title="Close Inspector"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
        <div className="px-4 border-b border-zinc-800/80 bg-zinc-950 shrink-0">
          <TabsList className="bg-transparent h-9 p-0 gap-4 border-0">
            <TabsTrigger
              value="overview"
              className="text-xs data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-amber-400 data-[state=active]:text-amber-400 rounded-none px-0 pb-2"
            >
              Overview
            </TabsTrigger>
            <TabsTrigger
              value="relations"
              className="text-xs data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-amber-400 data-[state=active]:text-amber-400 rounded-none px-0 pb-2"
            >
              Relations ({node.degree ?? 0})
            </TabsTrigger>
            <TabsTrigger
              value="provenance"
              className="text-xs data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-amber-400 data-[state=active]:text-amber-400 rounded-none px-0 pb-2"
            >
              Provenance
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Tab 1: Overview */}
          <TabsContent value="overview" className="space-y-4 m-0">
            <div>
              <div className="text-[10px] font-mono uppercase text-zinc-500 font-semibold mb-1">
                Description
              </div>
              <p className="text-zinc-300 leading-relaxed text-xs bg-zinc-900/40 p-2.5 rounded-lg border border-zinc-800/60">
                {node.description}
              </p>
            </div>

            {/* Connectivity summary */}
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 space-y-2">
              <div className="flex justify-between items-center text-[11px]">
                <span className="font-mono text-zinc-400">Graph Degree</span>
                <span className="font-mono font-semibold text-amber-400 tabular-nums">
                  {node.degree ?? 0}
                </span>
              </div>
              <div className="flex justify-between text-[10px] font-mono text-zinc-500">
                <span>Source: {node.source_kind || "unknown"}</span>
                <span>Tier {node.tier}</span>
              </div>
            </div>

            {/* Neighborhood summary */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-zinc-500 font-semibold">
                Neighborhood Summary
              </div>
              <div className="grid grid-cols-2 gap-2 text-center font-mono">
                <div className="p-2 rounded border border-zinc-800 bg-zinc-900/30">
                  <div className="text-zinc-400 text-[10px]">Downstream Targets</div>
                  <div className="text-base font-semibold text-zinc-100 tabular-nums">{outgoing.length}</div>
                </div>
                <div className="p-2 rounded border border-zinc-800 bg-zinc-900/30">
                  <div className="text-zinc-400 text-[10px]">Upstream Callers</div>
                  <div className="text-base font-semibold text-zinc-100 tabular-nums">{incoming.length}</div>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Tab 2: Relations */}
          <TabsContent value="relations" className="space-y-4 m-0">
            {outgoing.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-zinc-500 font-semibold">
                  Outgoing Connections ({outgoing.length})
                </div>
                <div className="space-y-1">
                  {outgoing.map((l, idx) => {
                    const tgtId = typeof l.target === "object" ? (l.target as any).id : l.target;
                    const tgtNode = nodes.find((n) => n.id === tgtId);
                    return (
                      <div
                        key={idx}
                        onClick={() => onSelectNode(tgtId)}
                        className="p-2 rounded border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-800/60 hover:border-zinc-700 transition-colors flex items-center justify-between cursor-pointer group"
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="text-[10px] font-mono text-amber-400 font-semibold">
                            {l.relation}
                          </span>
                          <span className="text-zinc-500">→</span>
                          <span className="text-zinc-200 group-hover:text-amber-300 font-medium truncate">
                            {tgtNode?.name || tgtId}
                          </span>
                        </div>
                        <ArrowRight className="h-3 w-3 text-zinc-500 group-hover:text-zinc-300 shrink-0" />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {incoming.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-zinc-500 font-semibold">
                  Incoming Connections ({incoming.length})
                </div>
                <div className="space-y-1">
                  {incoming.map((l, idx) => {
                    const srcId = typeof l.source === "object" ? (l.source as any).id : l.source;
                    const srcNode = nodes.find((n) => n.id === srcId);
                    return (
                      <div
                        key={idx}
                        onClick={() => onSelectNode(srcId)}
                        className="p-2 rounded border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-800/60 hover:border-zinc-700 transition-colors flex items-center justify-between cursor-pointer group"
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="text-zinc-200 group-hover:text-amber-300 font-medium truncate">
                            {srcNode?.name || srcId}
                          </span>
                          <span className="text-zinc-500">→</span>
                          <span className="text-[10px] font-mono text-zinc-400">
                            {l.relation}
                          </span>
                        </div>
                        <ArrowRight className="h-3 w-3 text-zinc-500 group-hover:text-zinc-300 shrink-0" />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </TabsContent>

          {/* Tab 3: Provenance */}
          <TabsContent value="provenance" className="space-y-3 m-0">
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Confidence Tier</span>
                <Badge
                  variant="outline"
                  className={`font-mono text-[10px] ${
                    node.tier === 1
                      ? "border-sky-400/40 text-sky-400 bg-sky-400/10"
                      : node.tier === 2
                      ? "border-emerald-400/40 text-emerald-400 bg-emerald-400/10"
                      : "border-amber-400/40 text-amber-400 bg-amber-400/10"
                  }`}
                >
                  Tier {node.tier || 1}: {node.tier === 1 ? "Authoritative" : node.tier === 2 ? "Derived" : "Inferred"}
                </Badge>
              </div>

              <div className="flex items-center justify-between py-1 border-t border-zinc-800/60">
                <span className="text-zinc-400">Source Kind</span>
                <span className="font-mono text-zinc-200">{node.source_kind || "unknown"}</span>
              </div>

              <div className="flex items-center justify-between py-1 border-t border-zinc-800/60">
                <span className="text-zinc-400">Ingestion Timestamp</span>
                <span className="font-mono text-zinc-200">{node.ingested_at || "—"}</span>
              </div>

              <div className="flex items-center justify-between py-1 border-t border-zinc-800/60">
                <span className="text-zinc-400">Extraction Method</span>
                <span className="font-mono text-zinc-200">GraphRAG LLM Triplet Parser</span>
              </div>
            </div>
          </TabsContent>
        </div>
      </Tabs>

      {/* Bottom Actions Bar */}
      <div className="p-4 border-t border-zinc-800/80 bg-zinc-900/40 space-y-3 shrink-0">
        {/* Find Path To selector */}
        <div className="flex items-center gap-2">
          <select
            value={selectedTarget}
            onChange={(e) => setSelectedTarget(e.target.value)}
            className="flex-1 h-7 rounded-md bg-zinc-900 border border-zinc-800 text-[11px] font-mono text-zinc-300 px-2 focus:outline-none"
          >
            <option value="">Find path to entity...</option>
            {nodes
              .filter((n) => n.id !== node.id)
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name} ({n.type})
                </option>
              ))}
          </select>

          <Button
            size="sm"
            disabled={!selectedTarget}
            onClick={() => {
              if (selectedTarget) {
                onFindPath(node.id, selectedTarget);
              }
            }}
            className="h-7 text-xs bg-amber-500 hover:bg-amber-400 text-zinc-950 font-medium px-2.5 cursor-pointer disabled:opacity-40"
          >
            <Sparkles className="h-3 w-3 mr-1" />
            Path
          </Button>
        </div>

        {/* Query & Filter buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyCypher}
            className="flex-1 h-7 text-[11px] font-mono border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 cursor-pointer"
          >
            {copiedCypher ? <Check className="h-3 w-3 mr-1 text-emerald-400" /> : <Copy className="h-3 w-3 mr-1" />}
            Copy Cypher
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              toast.info(`Isolated 1-hop neighborhood of ${node.name}`);
            }}
            className="h-7 text-[11px] font-mono border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 cursor-pointer"
            title="Filter to neighborhood"
          >
            <Layers className="h-3 w-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}

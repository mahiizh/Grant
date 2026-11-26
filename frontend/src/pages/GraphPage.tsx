import { useState, useCallback, useMemo, Suspense, lazy, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useGraph } from "../lib/api/hooks/useGraph";
import type { GraphLink, GraphNode } from "../types/graph";
import { GraphCanvas2D } from "../features/GraphCanvas2D";
import { GraphLegend } from "../features/GraphLegend";
import { GraphMinimap } from "../features/GraphMinimap";
import { NodeInspectorPanel } from "../features/NodeInspectorPanel";
import { EntityTable } from "../features/EntityTable";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "../components/ui/resizable";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "../components/ui/toggle-group";
import { Button } from "../components/ui/button";
import {
  Maximize2,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Table as TableIcon,
} from "lucide-react";
import { toast } from "sonner";

// Lazy-load 3D engine for performance and bundle splitting
const LazyGraphCanvas3D = lazy(() => import("../features/GraphCanvas3D"));

export function GraphPage() {
  const [searchParams] = useSearchParams();
  const initialNodeId = searchParams.get("node");

  // Graph state & controls
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d");
  const [colorBy, setColorBy] = useState<"type" | "tier">("type");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [zoomTrigger, setZoomTrigger] = useState(0);
  const [sourceKind, setSourceKind] = useState("");
  const [tableCollapsed, setTableCollapsed] = useState(false);

  // Active reasoning path state
  const [activePath, setActivePath] = useState<string[] | null>(null);
  const [highlightedPathNodes, setHighlightedPathNodes] = useState<Set<string>>(new Set());

  // API Hook for graph data
  const { data: graphResponse } = useGraph({
    sourceKind: sourceKind || undefined,
  });

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

  // Auto-select node if URL param provided
  useEffect(() => {
    if (initialNodeId) {
      setSelectedNodeId(initialNodeId);
    }
  }, [initialNodeId]);

  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  // Handle node selection
  const handleSelectNode = useCallback((nodeOrId: GraphNode | string) => {
    const id = typeof nodeOrId === "string" ? nodeOrId : nodeOrId.id;
    setSelectedNodeId(id);
  }, []);

  // Breadth-first path discovery across the returned graph topology.
  const handleFindPath = useCallback(
    (sourceId: string, targetId: string) => {
      const adjacency = new Map<string, string[]>();
      const addEdge = (from: string, to: string) => {
        const current = adjacency.get(from) ?? [];
        if (!current.includes(to)) current.push(to);
        adjacency.set(from, current);
      };

      links.forEach((l) => {
        const source = typeof l.source === "object" ? (l.source as any).id : l.source;
        const target = typeof l.target === "object" ? (l.target as any).id : l.target;
        if (typeof source === "string" && typeof target === "string") {
          addEdge(source, target);
          addEdge(target, source);
        }
      });

      const queue: string[] = [sourceId];
      const previous = new Map<string, string | null>([[sourceId, null]]);
      let found = false;

      while (queue.length > 0) {
        const current = queue.shift()!;
        if (current === targetId) {
          found = true;
          break;
        }
        for (const neighbor of adjacency.get(current) ?? []) {
          if (!previous.has(neighbor)) {
            previous.set(neighbor, current);
            queue.push(neighbor);
          }
        }
      }

      if (!found) {
        toast.error("No connected path discovered between these entities.");
        return;
      }

      const path: string[] = [];
      let cursor: string | null | undefined = targetId;
      while (cursor) {
        path.unshift(cursor);
        cursor = previous.get(cursor);
      }

      setActivePath(path);
      setHighlightedPathNodes(new Set(path));
      toast.success(`Discovered ${path.length - 1}-hop reasoning path`);
    },
    [links]
  );

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-zinc-950 select-none">
      {/* Single-line Top Toolbar */}
      <div className="h-11 px-4 border-b border-zinc-800/80 bg-zinc-950/90 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3">
          {/* 2D / 3D Switcher */}
          <Tabs
            value={viewMode}
            onValueChange={(val) => setViewMode(val as "2d" | "3d")}
            className="w-auto"
          >
            <TabsList className="bg-zinc-900 border border-zinc-800 h-7 p-0.5">
              <TabsTrigger value="2d" className="text-[11px] px-2 h-6">
                2D
              </TabsTrigger>
              <TabsTrigger value="3d" className="text-[11px] px-2 h-6">
                3D Bloom
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Color Encoding Toggle */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-zinc-400 border-l border-zinc-800/80 pl-3">
            <span className="text-[10px] font-mono text-zinc-500 uppercase">Color:</span>
            <ToggleGroup
              type="single"
              value={colorBy}
              onValueChange={(val) => {
                if (val) setColorBy(val as "type" | "tier");
              }}
              className="bg-zinc-900 border border-zinc-800 rounded-md p-0.5"
            >
              <ToggleGroupItem value="type" className="text-[10px] px-2 h-5 font-mono">
                Type
              </ToggleGroupItem>
              <ToggleGroupItem value="tier" className="text-[10px] px-2 h-5 font-mono">
                Tier
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {/* Source-kind filter */}
          <div className="hidden lg:flex items-center gap-1.5 text-xs text-zinc-400 border-l border-zinc-800/80 pl-3">
            <span className="text-[10px] font-mono text-zinc-500 uppercase">Source:</span>
            <select
              value={sourceKind}
              onChange={(event) => setSourceKind(event.target.value)}
              className="h-6 rounded-md border border-zinc-800 bg-zinc-900 px-1.5 text-[10px] font-mono text-zinc-300 outline-none hover:bg-zinc-800 focus:border-amber-500/40"
              aria-label="Filter graph by source kind"
            >
              <option value="">All</option>
              <option value="document">Docs</option>
              <option value="web">Web</option>
              <option value="chat">Chat</option>
              <option value="query">Query</option>
              <option value="answer">Answer</option>
            </select>
          </div>
        </div>

        {/* Muted Tabular Stats Bar & Actions */}
        <div className="flex items-center gap-3">
          <span className="hidden lg:inline text-xs font-mono text-zinc-400 tabular-nums">
            {nodes.length} entities · {links.length} relations
          </span>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setZoomTrigger((prev) => prev + 1)}
            className="h-7 text-[11px] font-mono border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 px-2"
          >
            <Maximize2 className="h-3 w-3 mr-1" />
            Fit
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setActivePath(null);
              setHighlightedPathNodes(new Set());
              setSelectedNodeId(null);
              setSourceKind("");
              setZoomTrigger((prev) => prev + 1);
              toast.info("Knowledge graph view reset");
            }}
            className="h-7 text-[11px] font-mono border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 px-2"
          >
            <RotateCcw className="h-3 w-3 mr-1" />
            Reset
          </Button>
        </div>
      </div>

      {/* Main Resizable Panel Structure */}
      <div className="flex-1 min-h-0">
        <ResizablePanelGroup orientation="vertical">
          {/* Top Panel: Canvas + Docked Inspector */}
          <ResizablePanel defaultSize={tableCollapsed ? "96%" : "68%"} minSize="40%">
            <ResizablePanelGroup orientation="horizontal">
              {/* Canvas Area (fills) */}
              <ResizablePanel defaultSize="70%" minSize="50%" className="relative">
                <div className="relative w-full h-full bg-[#09090b] overflow-hidden">
                  {viewMode === "2d" ? (
                    <GraphCanvas2D
                      nodes={nodes}
                      links={links}
                      colorBy={colorBy}
                      selectedNodeId={selectedNodeId}
                      activePath={activePath}
                      highlightedPathNodes={highlightedPathNodes}
                      onSelectNode={handleSelectNode}
                      zoomToTrigger={zoomTrigger}
                    />
                  ) : (
                    <Suspense
                      fallback={
                        <div className="w-full h-full flex items-center justify-center text-zinc-500 font-mono text-xs">
                          Loading 3D Engine & UnrealBloom...
                        </div>
                      }
                    >
                      <LazyGraphCanvas3D
                        nodes={nodes}
                        links={links}
                        colorBy={colorBy}
                        selectedNodeId={selectedNodeId}
                        activePath={activePath}
                        highlightedPathNodes={highlightedPathNodes}
                        onSelectNode={handleSelectNode}
                        zoomToTrigger={zoomTrigger}
                      />
                    </Suspense>
                  )}

                  {/* Bottom-Left Collapsible Legend */}
                  <GraphLegend colorBy={colorBy} />

                  {/* Bottom-Right Minimap */}
                  <GraphMinimap
                    nodes={nodes}
                    links={links}
                    selectedNodeId={selectedNodeId}
                  />
                </div>
              </ResizablePanel>

              {/* Resizable Divider between Canvas and Inspector */}
              <ResizableHandle withHandle orientation="horizontal" />

              {/* Docked Inspector Panel (Non-modal) */}
              <ResizablePanel
                defaultSize="30%"
                minSize="20%"
                maxSize="45%"
                collapsible
              >
                <NodeInspectorPanel
                  node={selectedNode}
                  nodes={nodes}
                  links={links}
                  onSelectNode={(id) => setSelectedNodeId(id)}
                  onFindPath={handleFindPath}
                  onClose={() => setSelectedNodeId(null)}
                />
              </ResizablePanel>
            </ResizablePanelGroup>
          </ResizablePanel>

          {/* Resizable Divider between Canvas and Entity Table with toggle button */}
          <div className="relative flex items-center justify-center">
            <ResizableHandle withHandle orientation="vertical" className="w-full" />
            <button
              onClick={() => setTableCollapsed(!tableCollapsed)}
              className="absolute z-20 px-2 py-0.5 rounded-full border border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors text-[10px] font-mono flex items-center gap-1 cursor-pointer shadow-md"
              title={tableCollapsed ? "Expand Entity Table" : "Collapse Entity Table"}
            >
              <TableIcon className="h-3 w-3" />
              <span>Table</span>
              {tableCollapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>

          {/* Bottom Panel: Collapsible Entity Table */}
          {!tableCollapsed && (
            <ResizablePanel defaultSize="32%" minSize="14%" collapsible>
              <EntityTable
                nodes={nodes}
                selectedNodeId={selectedNodeId}
                onSelectNode={(id) => setSelectedNodeId(id)}
              />
            </ResizablePanel>
          )}
        </ResizablePanelGroup>
      </div>
    </div>
  );
}

export default GraphPage;

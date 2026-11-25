import { useState, useCallback, useMemo, Suspense, lazy } from "react";
import { useSearchParams } from "react-router-dom";
import { useGraph } from "../lib/api/hooks/useGraph";
import { useGraphAnalytics, EnrichedNode } from "../hooks/useGraphAnalytics";
import { GraphCanvas2D } from "../features/GraphCanvas2D";
import { GraphLegend } from "../features/GraphLegend";
import { TemporalScrubber } from "../features/TemporalScrubber";
import { PathPlaybackOverlay } from "../features/PathPlaybackOverlay";
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
  const [colorBy, setColorBy] = useState<"type" | "cluster" | "tier">("type");
  const [layoutMode, setLayoutMode] = useState<"force" | "clustered">("force");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [zoomTrigger, setZoomTrigger] = useState(0);
  const [asOfDate, setAsOfDate] = useState("2026-04-12");
  const [sourceKind, setSourceKind] = useState("");
  const [tableCollapsed, setTableCollapsed] = useState(false);

  // Active reasoning path state
  const [activePath, setActivePath] = useState<string[] | null>([
    "outbox",
    "postgres",
    "data_platform",
    "alice_chen",
  ]);
  const [highlightedPathNodes, setHighlightedPathNodes] = useState<Set<string>>(
    new Set(["outbox", "postgres", "data_platform", "alice_chen"])
  );

  // API Hook for graph data
  const { data: graphResponse } = useGraph({
    asOf: asOfDate,
    sourceKind: sourceKind || undefined,
  });

  const graphData = useMemo(() => {
    if (!graphResponse) {
      return { nodes: [], links: [] };
    }
    return {
      nodes: graphResponse.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        type: n.type as any,
        description: (n as any).description || `${n.type} node`,
        valid_from: n.valid_from ?? "",
        valid_to: n.valid_to ?? "9999-12-31",
        tx_time: n.tx_time ?? "",
        tier: (n as any).tier || 1,
        chunkHash: (n as any).chunk_hash || "",
        // Backend analytics are optional; the worker recomputes them.
        cluster: n.community ?? undefined,
        pageRank: n.pagerank ?? undefined,
        degree: n.degree,
      })),
      links: graphResponse.links.map((l) => ({
        source: l.source,
        target: l.target,
        relation: l.label,
        tier: (l.tier as any) || 1,
        valid_from: l.valid_from ?? undefined,
      })),
    };
  }, [graphResponse]);

  // Graphology Analytics Hook
  const { nodes, links, clusters, stats, findPath } = useGraphAnalytics(graphData);

  // Auto-select node if URL param provided
  useState(() => {
    if (initialNodeId) {
      setSelectedNodeId(initialNodeId);
    }
  });

  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  // Handle node selection
  const handleSelectNode = useCallback(
    (nodeOrId: EnrichedNode | string) => {
      const id = typeof nodeOrId === "string" ? nodeOrId : nodeOrId.id;
      setSelectedNodeId(id);
    },
    []
  );

  // Handle Path Finding with animated step sequencing
  const handleFindPath = useCallback(
    (sourceId: string, targetId: string) => {
      const path = findPath(sourceId, targetId);
      if (!path || path.length < 2) {
        toast.error("No connected path discovered between these entities.");
        return;
      }

      setActivePath(path);
      setHighlightedPathNodes(new Set());
      toast.success(`Discovered ${path.length - 1}-hop reasoning path`);

      path.forEach((nodeId, idx) => {
        setTimeout(() => {
          setHighlightedPathNodes((prev) => new Set([...prev, nodeId]));
        }, idx * 150);
      });
    },
    [findPath]
  );

  // Stepping through path hops via playback overlay
  const handleSelectHop = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      setHighlightedPathNodes((prev) => new Set([...prev, nodeId]));
    },
    []
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
                if (val) setColorBy(val as "type" | "cluster" | "tier");
              }}
              className="bg-zinc-900 border border-zinc-800 rounded-md p-0.5"
            >
              <ToggleGroupItem value="type" className="text-[10px] px-2 h-5 font-mono">
                Type
              </ToggleGroupItem>
              <ToggleGroupItem value="cluster" className="text-[10px] px-2 h-5 font-mono">
                Cluster
              </ToggleGroupItem>
              <ToggleGroupItem value="tier" className="text-[10px] px-2 h-5 font-mono">
                Tier
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {/* Layout Mode */}
          <div className="hidden md:flex items-center gap-1.5 text-xs text-zinc-400 border-l border-zinc-800/80 pl-3">
            <span className="text-[10px] font-mono text-zinc-500 uppercase">Layout:</span>
            <ToggleGroup
              type="single"
              value={layoutMode}
              onValueChange={(val) => {
                if (val) setLayoutMode(val as "force" | "clustered");
              }}
              className="bg-zinc-900 border border-zinc-800 rounded-md p-0.5"
            >
              <ToggleGroupItem value="force" className="text-[10px] px-2 h-5 font-mono">
                Force
              </ToggleGroupItem>
              <ToggleGroupItem value="clustered" className="text-[10px] px-2 h-5 font-mono">
                Clustered
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
            {stats.totalEntities} entities · {stats.totalRelationships} relations · {stats.clustersDetected} clusters · avg depth {stats.avgPathDepth.toFixed(2)}
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
                      filterDate={asOfDate}
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

                  {/* Overlay 1: Top Reasoning Path Playback */}
                  {activePath && (
                    <PathPlaybackOverlay
                      path={activePath}
                      nodes={nodes}
                      onSelectHop={handleSelectHop}
                      onDismiss={() => setActivePath(null)}
                    />
                  )}

                  {/* Overlay 2: Bottom-Left Collapsible Legend */}
                  <GraphLegend colorBy={colorBy} clusters={clusters} />

                  {/* Overlay 3: Bottom-Center Bi-Temporal Scrubber */}
                  <TemporalScrubber
                    currentDate={asOfDate}
                    onDateChange={setAsOfDate}
                  />

                  {/* Overlay 4: Bottom-Right Minimap */}
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

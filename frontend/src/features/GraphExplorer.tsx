import React, { useState } from "react";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Network, ZoomIn, ZoomOut, RotateCcw, Info } from "lucide-react";

interface Node {
  id: string;
  name: string;
  type: "DATABASE" | "SERVICE" | "TEAM" | "PERSON" | "INCIDENT" | "MECHANISM" | "CONCEPT";
  x: number;
  y: number;
}

interface Edge {
  id: string;
  source: string;
  target: string;
  label: string;
}

const NODES: Node[] = [
  { id: "outbox", name: "Outbox", type: "MECHANISM", x: 120, y: 150 },
  { id: "postgres", name: "PostgreSQL", type: "DATABASE", x: 280, y: 150 },
  { id: "data_platform", name: "Data Platform Team", type: "TEAM", x: 460, y: 150 },
  { id: "alice_chen", name: "Alice Chen", type: "PERSON", x: 650, y: 150 },
  { id: "neo4j", name: "Neo4j", type: "DATABASE", x: 280, y: 60 },
  { id: "qdrant", name: "Qdrant", type: "DATABASE", x: 280, y: 240 },
  { id: "bob_kumar", name: "Bob Kumar", type: "PERSON", x: 120, y: 350 },
  { id: "inc_04", name: "INC-2026-04", type: "INCIDENT", x: 280, y: 350 },
  { id: "payment_gw", name: "PaymentGateway", type: "SERVICE", x: 460, y: 350 },
  { id: "payments_team", name: "Payments Team", type: "TEAM", x: 620, y: 350 },
  { id: "elena_rostova", name: "Elena Rostova", type: "PERSON", x: 780, y: 350 },
  { id: "core_banking", name: "CoreBanking", type: "SERVICE", x: 460, y: 450 },
  { id: "core_team", name: "Core Banking Team", type: "TEAM", x: 620, y: 450 },
  { id: "dave_miller", name: "Dave Miller", type: "PERSON", x: 780, y: 450 },
];

const EDGES: Edge[] = [
  { id: "e1", source: "outbox", target: "postgres", label: "STAGED_IN" },
  { id: "e2", source: "postgres", target: "data_platform", label: "OWNED_BY" },
  { id: "e3", source: "data_platform", target: "alice_chen", label: "LED_BY" },
  { id: "e4", source: "neo4j", target: "data_platform", label: "OWNED_BY" },
  { id: "e5", source: "qdrant", target: "data_platform", label: "OWNED_BY" },
  { id: "e6", source: "bob_kumar", target: "inc_04", label: "COMMANDED" },
  { id: "e7", source: "inc_04", target: "payment_gw", label: "IMPACTED" },
  { id: "e8", source: "payment_gw", target: "payments_team", label: "OWNED_BY" },
  { id: "e9", source: "payments_team", target: "elena_rostova", label: "LED_BY" },
  { id: "e10", source: "inc_04", target: "core_banking", label: "CAUSED_BY" },
  { id: "e11", source: "core_banking", target: "core_team", label: "OWNED_BY" },
  { id: "e12", source: "core_team", target: "dave_miller", label: "LED_BY" },
];

const TYPE_COLORS: Record<Node["type"], { bg: string; border: string; text: string }> = {
  DATABASE: { bg: "#1e3a8a", border: "#3b82f6", text: "#93c5fd" },
  SERVICE: { bg: "#065f46", border: "#10b981", text: "#6ee7b7" },
  TEAM: { bg: "#581c87", border: "#a855f7", text: "#d8b4fe" },
  PERSON: { bg: "#701a75", border: "#d946ef", text: "#f5d0fe" },
  INCIDENT: { bg: "#881337", border: "#f43f5e", text: "#fecdd3" },
  MECHANISM: { bg: "#78350f", border: "#f59e0b", text: "#fde68a" },
  CONCEPT: { bg: "#3f3f46", border: "#71717a", text: "#e4e4e7" },
};

export function GraphExplorer({ activePath }: { activePath?: string[] | null }) {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [zoom, setZoom] = useState(1);

  // Normalize path nodes for matching
  const pathTokens = activePath ? activePath.map((t) => t.toLowerCase().trim()) : [];

  const isNodeInPath = (nodeName: string) => {
    if (!pathTokens.length) return false;
    return pathTokens.includes(nodeName.toLowerCase().trim());
  };

  const isEdgeInPath = (edge: Edge) => {
    if (!pathTokens.length) return false;
    const srcNode = NODES.find((n) => n.id === edge.source);
    const tgtNode = NODES.find((n) => n.id === edge.target);
    if (!srcNode || !tgtNode) return false;
    return (
      pathTokens.includes(srcNode.name.toLowerCase().trim()) &&
      pathTokens.includes(tgtNode.name.toLowerCase().trim())
    );
  };

  return (
    <Card className="flex flex-col h-full border-zinc-800 bg-zinc-900/60">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3 border-b border-zinc-800/60">
        <div>
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <Network className="h-4 w-4 text-purple-400" />
            Knowledge Graph & Multi-Hop Path Visualizer
          </CardTitle>
          <CardDescription>
            Live bi-temporal knowledge graph discovered across documents. Highlights traversal paths in real-time.
          </CardDescription>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.15, 1.8))}
            className="p-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.15, 0.6))}
            className="p-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            onClick={() => setZoom(1)}
            className="p-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Reset Zoom"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-4 flex flex-col justify-between">
        {/* Active Path Banner */}
        {activePath && activePath.length > 0 && (
          <div className="mb-3 p-3 rounded-lg border border-purple-500/30 bg-purple-950/30 flex items-center gap-2 text-xs">
            <span className="font-semibold text-purple-400 uppercase tracking-wider text-[10px]">
              Multi-Hop Traversal:
            </span>
            <div className="flex items-center gap-1.5 flex-wrap">
              {activePath.map((step, idx) => (
                <React.Fragment key={idx}>
                  {idx % 2 === 0 ? (
                    <Badge variant="graph" className="text-[11px] py-0 px-2">
                      {step}
                    </Badge>
                  ) : (
                    <span className="text-zinc-500 font-mono text-[10px] font-bold">
                      ── {step} ──&gt;
                    </span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {/* SVG Graph Canvas */}
        <div className="relative border border-zinc-800/80 rounded-xl bg-zinc-950/80 overflow-hidden flex-1 min-h-[380px] flex items-center justify-center">
          <svg
            viewBox="0 0 900 520"
            className="w-full h-full cursor-grab active:cursor-grabbing transition-transform duration-200"
            style={{ transform: `scale(${zoom})` }}
          >
            <defs>
              <marker
                id="arrow"
                viewBox="0 0 10 10"
                refX="22"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#71717a" />
              </marker>
              <marker
                id="arrow-active"
                viewBox="0 0 10 10"
                refX="22"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#c084fc" />
              </marker>
            </defs>

            {/* Edges */}
            {EDGES.map((edge) => {
              const src = NODES.find((n) => n.id === edge.source);
              const tgt = NODES.find((n) => n.id === edge.target);
              if (!src || !tgt) return null;

              const active = isEdgeInPath(edge);

              return (
                <g key={edge.id}>
                  <line
                    x1={src.x}
                    y1={src.y}
                    x2={tgt.x}
                    y2={tgt.y}
                    stroke={active ? "#c084fc" : "#3f3f46"}
                    strokeWidth={active ? "3" : "1.5"}
                    strokeDasharray={active ? "none" : "none"}
                    markerEnd={active ? "url(#arrow-active)" : "url(#arrow)"}
                    className="transition-all duration-300"
                  />
                  {/* Edge label */}
                  <rect
                    x={(src.x + tgt.x) / 2 - 28}
                    y={(src.y + tgt.y) / 2 - 8}
                    width="56"
                    height="16"
                    rx="3"
                    fill={active ? "#581c87" : "#18181b"}
                    stroke={active ? "#a855f7" : "#27272a"}
                    strokeWidth="1"
                  />
                  <text
                    x={(src.x + tgt.x) / 2}
                    y={(src.y + tgt.y) / 2 + 3}
                    textAnchor="middle"
                    fill={active ? "#f3e8ff" : "#a1a1aa"}
                    fontSize="8.5"
                    fontFamily="monospace"
                    fontWeight={active ? "bold" : "normal"}
                  >
                    {edge.label}
                  </text>
                </g>
              );
            })}

            {/* Nodes */}
            {NODES.map((node) => {
              const style = TYPE_COLORS[node.type];
              const active = isNodeInPath(node.name);
              const selected = selectedNode?.id === node.id;

              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  className="cursor-pointer group"
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={active ? 24 : 20}
                    fill={active ? "#581c87" : style.bg}
                    stroke={active ? "#e879f9" : selected ? "#ffffff" : style.border}
                    strokeWidth={active ? 3.5 : selected ? 3 : 1.5}
                    className="transition-all duration-300 group-hover:filter group-hover:brightness-125"
                  />
                  <text
                    x={node.x}
                    y={node.y + 32}
                    textAnchor="middle"
                    fill={active ? "#fdf4ff" : "#e4e4e7"}
                    fontSize="10"
                    fontWeight={active ? "bold" : "normal"}
                    className="select-none pointer-events-none drop-shadow"
                  >
                    {node.name}
                  </text>
                  <text
                    x={node.x}
                    y={node.y + 43}
                    textAnchor="middle"
                    fill="#71717a"
                    fontSize="7.5"
                    fontFamily="monospace"
                    className="select-none pointer-events-none"
                  >
                    {node.type}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Node Inspector Floating Dialog */}
          {selectedNode && (
            <div className="absolute bottom-3 right-3 p-3 bg-zinc-900/90 border border-zinc-700/80 rounded-xl shadow-xl backdrop-blur max-w-xs text-xs">
              <div className="flex items-center justify-between pb-1 border-b border-zinc-800">
                <span className="font-semibold text-zinc-100">{selectedNode.name}</span>
                <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                  {selectedNode.type}
                </Badge>
              </div>
              <p className="text-zinc-400 mt-2 text-[11px]">
                Coordinates: ({selectedNode.x}, {selectedNode.y}). Indexed in Neo4j 5 graph cluster.
              </p>
              <button
                onClick={() => setSelectedNode(null)}
                className="mt-2 text-zinc-500 hover:text-zinc-300 underline text-[10px]"
              >
                Close Inspector
              </button>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-between text-xs text-zinc-400 border-t border-zinc-800/60 pt-3">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-blue-500 inline-block" /> Database
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 inline-block" /> Service
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-purple-500 inline-block" /> Team
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-pink-500 inline-block" /> Person
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500 inline-block" /> Incident
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-500 inline-block" /> Mechanism
            </span>
          </div>
          <div className="flex items-center gap-1 text-[11px] text-zinc-500">
            <Info className="h-3.5 w-3.5" /> Click any node to inspect metadata
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

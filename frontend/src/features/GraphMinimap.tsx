import { useMemo } from "react";
import { EnrichedNode } from "../hooks/useGraphAnalytics";
import { GraphLink } from "../types/graph";

export interface GraphMinimapProps {
  nodes: EnrichedNode[];
  links: GraphLink[];
  selectedNodeId: string | null;
  onMinimapClick?: (x: number, y: number) => void;
}

const TYPE_COLORS: Record<string, string> = {
  mechanism: "#F59E0B",
  database: "#38BDF8",
  person: "#8B5CF6",
  team: "#8B5CF6",
  service: "#10B981",
};

export function GraphMinimap({
  nodes,
  selectedNodeId,
  onMinimapClick,
}: GraphMinimapProps) {
  const width = 160;
  const height = 110;
  const padding = 12;

  // Compute bounding box of node positions
  const bounds = useMemo(() => {
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    nodes.forEach((n: any) => {
      const x = n.x ?? 0;
      const y = n.y ?? 0;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    });

    if (minX === Infinity) {
      return { minX: -200, maxX: 200, minY: -150, maxY: 150 };
    }

    // Add margin
    const dx = Math.max(maxX - minX, 100);
    const dy = Math.max(maxY - minY, 100);

    return {
      minX: minX - dx * 0.1,
      maxX: maxX + dx * 0.1,
      minY: minY - dy * 0.1,
      maxY: maxY + dy * 0.1,
    };
  }, [nodes]);

  // Transform world coordinates (x, y) to minimap pixel (mx, my)
  const toMini = (wx: number, wy: number) => {
    const rx = (wx - bounds.minX) / (bounds.maxX - bounds.minX || 1);
    const ry = (wy - bounds.minY) / (bounds.maxY - bounds.minY || 1);
    const mx = padding + rx * (width - 2 * padding);
    const my = padding + ry * (height - 2 * padding);
    return { mx, my };
  };

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onMinimapClick) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const rx = (clickX - padding) / (width - 2 * padding);
    const ry = (clickY - padding) / (height - 2 * padding);

    const worldX = bounds.minX + rx * (bounds.maxX - bounds.minX);
    const worldY = bounds.minY + ry * (bounds.maxY - bounds.minY);

    onMinimapClick(worldX, worldY);
  };

  return (
    <div className="absolute bottom-4 right-4 z-10 w-[160px] h-[110px] rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md shadow-xl overflow-hidden select-none pointer-events-auto">
      <div className="absolute top-1 left-2 text-[9px] font-mono text-zinc-500 uppercase tracking-wider">
        Minimap
      </div>
      <svg
        width={width}
        height={height}
        className="w-full h-full cursor-crosshair"
        onClick={handleClick}
      >
        {/* Render node dots */}
        {nodes.map((node: any) => {
          const { mx, my } = toMini(node.x ?? 0, node.y ?? 0);
          const isSelected = node.id === selectedNodeId;
          const color = TYPE_COLORS[node.type] || "#8B5CF6";

          return (
            <circle
              key={node.id}
              cx={mx}
              cy={my}
              r={isSelected ? 4 : 2}
              fill={isSelected ? "#FFFFFF" : color}
              stroke={isSelected ? "#38BDF8" : "none"}
              strokeWidth={1.5}
              opacity={0.85}
            />
          );
        })}

        {/* Viewport Frame Box indicator */}
        <rect
          x={width * 0.25}
          y={height * 0.22}
          width={width * 0.5}
          height={height * 0.55}
          fill="rgba(56, 189, 248, 0.05)"
          stroke="rgba(56, 189, 248, 0.4)"
          strokeWidth={1}
          strokeDasharray="2 2"
          rx={3}
        />
      </svg>
    </div>
  );
}

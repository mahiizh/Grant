import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { GraphLink, GraphNode } from "../types/graph";
import { NodeContextMenu } from "./NodeContextMenu";
import { useApp } from "../context/AppContext";
import { toast } from "sonner";

export interface GraphCanvas2DProps {
  nodes: GraphNode[];
  links: GraphLink[];
  colorBy: "type" | "tier";
  selectedNodeId: string | null;
  onSelectNode: (node: GraphNode) => void;
  activePath: string[] | null;
  highlightedPathNodes: Set<string>;
  zoomToTrigger: number;
  onFindPathRequest?: (sourceId: string) => void;
}

const TYPE_COLORS: Record<string, string> = {
  mechanism: "#F59E0B",
  database: "#38BDF8",
  person: "#8B5CF6",
  team: "#8B5CF6",
  service: "#10B981",
};

const TIER_COLORS: Record<number, string> = {
  1: "#38BDF8",
  2: "#10B981",
  3: "#F59E0B",
};

const GLYPH_MAP: Record<string, string> = {
  mechanism: "M",
  database: "D",
  person: "P",
  team: "T",
  service: "S",
};

export function GraphCanvas2D({
  nodes,
  links,
  colorBy,
  selectedNodeId,
  onSelectNode,
  activePath,
  highlightedPathNodes,
  zoomToTrigger,
  onFindPathRequest,
}: GraphCanvas2DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const { theme, canvasTheme } = useApp();
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [hoverNode, setHoverNode] = useState<GraphNode | null>(null);

  // Hidden nodes state (e.g. from context menu)
  const [hiddenNodeIds, setHiddenNodeIds] = useState<Set<string>>(new Set());

  // Right-click context menu state
  const [contextMenu, setContextMenu] = useState<{
    node: GraphNode;
    position: { x: number; y: number };
  } | null>(null);

  // Canvas background color (Item 5)
  const isLightCanvas = canvasTheme === "match" && theme === "light";
  const canvasBg = isLightCanvas ? "#f8fafc" : "#09090b";

  // Filter out hidden nodes
  const visibleNodes = useMemo(() => {
    if (hiddenNodeIds.size === 0) return nodes;
    return nodes.filter((n) => !hiddenNodeIds.has(n.id));
  }, [nodes, hiddenNodeIds]);

  const visibleLinks = useMemo(() => {
    if (hiddenNodeIds.size === 0) return links;
    return links.filter((l) => {
      const s = typeof l.source === "object" ? (l.source as any).id : l.source;
      const t = typeof l.target === "object" ? (l.target as any).id : l.target;
      return !hiddenNodeIds.has(s) && !hiddenNodeIds.has(t);
    });
  }, [links, hiddenNodeIds]);

  // Referentially stable graph data (Item 2)
  const stableGraphData = useMemo(() => ({
    nodes: visibleNodes,
    links: visibleLinks,
  }), [visibleNodes, visibleLinks]);

  // Reduced motion preference
  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  // ResizeObserver for canvas dimensions
  useEffect(() => {
    if (!containerRef.current) return;
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Pause animation when hidden or off-screen (Item 2)
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (fgRef.current) {
        if (entry.isIntersecting) {
          fgRef.current.resumeAnimation();
        } else {
          fgRef.current.pauseAnimation();
        }
      }
    });

    observer.observe(containerRef.current);

    const handleVisibility = () => {
      if (!fgRef.current) return;
      if (document.hidden) {
        fgRef.current.pauseAnimation();
      } else {
        fgRef.current.resumeAnimation();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  // Set of active path links
  const activePathLinkKeys = useMemo(() => {
    const keys = new Set<string>();
    if (!activePath || activePath.length < 2) return keys;

    for (let i = 0; i < activePath.length - 1; i++) {
      const src = activePath[i];
      const tgt = activePath[i + 1];
      keys.add(`${src}->${tgt}`);
      keys.add(`${tgt}->${src}`);
    }
    return keys;
  }, [activePath]);

  // Set of neighbor node IDs for hovered node
  const hoverNeighbors = useMemo(() => {
    const neighbors = new Set<string>();
    if (!hoverNode) return neighbors;
    neighbors.add(hoverNode.id);

    visibleLinks.forEach((l) => {
      const srcId = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgtId = typeof l.target === "object" ? (l.target as any).id : l.target;
      if (srcId === hoverNode.id) neighbors.add(tgtId);
      if (tgtId === hoverNode.id) neighbors.add(srcId);
    });

    return neighbors;
  }, [hoverNode, visibleLinks]);

  // Zoom to fit on engine stop
  const handleEngineStop = useCallback(() => {
    if (fgRef.current) {
      fgRef.current.zoomToFit(prefersReducedMotion ? 0 : 600, 30);
    }
  }, [prefersReducedMotion]);

  // Programmatic zoom trigger
  useEffect(() => {
    if (zoomToTrigger > 0 && fgRef.current) {
      fgRef.current.zoomToFit(prefersReducedMotion ? 0 : 600, 30);
    }
  }, [zoomToTrigger, prefersReducedMotion]);

  // Focus on selected node
  useEffect(() => {
    if (selectedNodeId && fgRef.current) {
      const n = visibleNodes.find((node) => node.id === selectedNodeId);
      if (n && (n as any).x !== undefined && (n as any).y !== undefined) {
        fgRef.current.centerAt((n as any).x, (n as any).y, prefersReducedMotion ? 0 : 800);
        fgRef.current.zoom(2.2, prefersReducedMotion ? 0 : 800);
      }
    }
  }, [selectedNodeId, visibleNodes, prefersReducedMotion]);

  // Helper to determine node color
  const getNodeColor = useCallback(
    (node: GraphNode): string => {
      if (colorBy === "tier") {
        return TIER_COLORS[node.tier || 1] || "#38BDF8";
      }
      return TYPE_COLORS[node.type] || "#8B5CF6";
    },
    [colorBy]
  );

  // Background dot-grid pattern via onRenderFramePre
  const handleRenderFramePre = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      const transform = ctx.getTransform();
      const minX = -transform.e / transform.a;
      const minY = -transform.f / transform.d;
      const maxX = minX + ctx.canvas.width / transform.a;
      const maxY = minY + ctx.canvas.height / transform.d;

      const step = 32;
      const startX = Math.floor(minX / step) * step;
      const endX = Math.ceil(maxX / step) * step;
      const startY = Math.floor(minY / step) * step;
      const endY = Math.ceil(maxY / step) * step;

      ctx.save();
      ctx.fillStyle = isLightCanvas ? "rgba(0, 0, 0, 0.05)" : "rgba(255, 255, 255, 0.035)";
      for (let x = startX; x <= endX; x += step) {
        for (let y = startY; y <= endY; y += step) {
          ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
        }
      }
      ctx.restore();
    },
    [isLightCanvas]
  );

  // Custom node painting with crisp borders and strict glow budget
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSelected = selectedNodeId === node.id;
      const isHovered = hoverNode?.id === node.id;
      const isPathNode = highlightedPathNodes.has(node.id);
      const isDimmed = hoverNode !== null && !hoverNeighbors.has(node.id);

      const color = getNodeColor(node);
      const radius = node.val || 6;
      const screenRadius = radius * globalScale;

      ctx.save();

      if (isDimmed) {
        ctx.globalAlpha = 0.15;
      }

      // Glow ONLY on hover, selected, or active path
      if (isHovered || isSelected || isPathNode) {
        ctx.shadowColor = isPathNode ? "#F59E0B" : isSelected ? "#38BDF8" : color;
        ctx.shadowBlur = isSelected ? 24 : isHovered ? 18 : 14;
      } else {
        ctx.shadowBlur = 0;
      }

      // Core Circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = isPathNode ? "#F59E0B" : color;
      ctx.fill();

      // Crisp 1px border
      ctx.lineWidth = (isSelected || isPathNode ? 2 : 1) / globalScale;
      ctx.strokeStyle = isSelected
        ? "#FFFFFF"
        : isPathNode
        ? "#FDE68A"
        : isLightCanvas
        ? "rgba(0, 0, 0, 0.3)"
        : "rgba(255, 255, 255, 0.25)";
      ctx.stroke();

      // Draw node glyph letter inside circle
      if (screenRadius > 5) {
        ctx.shadowBlur = 0;
        const glyph = GLYPH_MAP[node.type] || "•";
        const glyphSize = Math.max(radius * 0.9, 3);
        ctx.font = `600 ${glyphSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = isPathNode ? "#09090b" : "#FFFFFF";
        ctx.fillText(glyph, node.x, node.y);
      }

      ctx.shadowBlur = 0;

      // Draw label
      const shouldDrawLabel =
        (globalScale > 1.2 && screenRadius > 4) || isHovered || isSelected || isPathNode;

      if (shouldDrawLabel && !isDimmed) {
        const label = node.name;
        const fontSize = Math.max(10 / globalScale, 3);
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        const textWidth = ctx.measureText(label).width;
        const padding = 2 / globalScale;
        const bgY = node.y + radius + 3 / globalScale;

        ctx.fillStyle = isLightCanvas ? "rgba(255, 255, 255, 0.9)" : "rgba(9, 9, 11, 0.85)";
        ctx.fillRect(
          node.x - textWidth / 2 - padding,
          bgY - padding,
          textWidth + padding * 2,
          fontSize + padding * 2
        );

        ctx.fillStyle = isPathNode
          ? "#F59E0B"
          : isSelected
          ? (isLightCanvas ? "#09090b" : "#FFFFFF")
          : (isLightCanvas ? "#18181b" : "#E4E4E7");
        ctx.fillText(label, node.x, bgY);
      }

      ctx.restore();
    },
    [selectedNodeId, hoverNode, hoverNeighbors, highlightedPathNodes, getNodeColor, isLightCanvas]
  );

  // Link directional particles
  const getLinkParticles = useCallback(
    (link: any) => {
      if (prefersReducedMotion) return 0;
      const srcId = typeof link.source === "object" ? link.source.id : link.source;
      const tgtId = typeof link.target === "object" ? link.target.id : link.target;
      return activePathLinkKeys.has(`${srcId}->${tgtId}`) ? 5 : 0;
    },
    [activePathLinkKeys, prefersReducedMotion]
  );

  // Link color with provenance tier encoding
  const getLinkColor = useCallback(
    (link: any) => {
      const srcId = typeof link.source === "object" ? link.source.id : link.source;
      const tgtId = typeof link.target === "object" ? link.target.id : link.target;
      const isPathLink = activePathLinkKeys.has(`${srcId}->${tgtId}`);
      if (isPathLink) return "#F59E0B";

      if (hoverNode) {
        if (hoverNeighbors.has(srcId) && hoverNeighbors.has(tgtId)) {
          return isLightCanvas ? "rgba(0, 0, 0, 0.6)" : "rgba(255, 255, 255, 0.6)";
        }
        return isLightCanvas ? "rgba(0, 0, 0, 0.04)" : "rgba(255, 255, 255, 0.02)";
      }

      const tier = link.tier || 1;
      if (tier === 3) return "rgba(245, 158, 11, 0.4)";
      if (tier === 2) return isLightCanvas ? "rgba(0, 0, 0, 0.12)" : "rgba(255, 255, 255, 0.15)";
      return isLightCanvas ? "rgba(0, 0, 0, 0.25)" : "rgba(255, 255, 255, 0.35)";
    },
    [activePathLinkKeys, hoverNode, hoverNeighbors, isLightCanvas]
  );

  const getLinkWidth = useCallback(
    (link: any) => {
      const srcId = typeof link.source === "object" ? link.source.id : link.source;
      const tgtId = typeof link.target === "object" ? link.target.id : link.target;
      return activePathLinkKeys.has(`${srcId}->${tgtId}`) ? 2.5 : (link.tier === 1 ? 1.5 : 1.0);
    },
    [activePathLinkKeys]
  );

  const getLinkLineDash = useCallback(
    (link: any): number[] | null => {
      const srcId = typeof link.source === "object" ? link.source.id : link.source;
      const tgtId = typeof link.target === "object" ? link.target.id : link.target;
      if (activePathLinkKeys.has(`${srcId}->${tgtId}`)) return null;
      return link.tier === 3 ? [3, 3] : null;
    },
    [activePathLinkKeys]
  );

  // Context Menu handlers
  const handleExpandNeighbors = (node: GraphNode) => {
    onSelectNode(node);
    toast.info(`Focused neighborhood of ${node.name}`);
  };

  const handleFindPathFromHere = (node: GraphNode) => {
    if (onFindPathRequest) {
      onFindPathRequest(node.id);
    } else {
      toast.info(`Selected ${node.name} as path source`);
    }
  };

  const handleHideNode = (node: GraphNode) => {
    setHiddenNodeIds((prev) => new Set([...prev, node.id]));
    toast.info(`Hidden node "${node.name}" from current canvas view`);
  };

  const handlePinNode = (node: any) => {
    if (node.fx !== undefined && node.fx !== null) {
      delete node.fx;
      delete node.fy;
      toast.info(`Unpinned ${node.name}`);
    } else {
      node.fx = node.x;
      node.fy = node.y;
      toast.success(`Pinned ${node.name} at (${Math.round(node.x)}, ${Math.round(node.y)})`);
    }
  };

  return (
    <div
      ref={containerRef}
      style={{ backgroundColor: canvasBg }}
      className="relative w-full h-full rounded-none overflow-hidden cursor-grab active:cursor-grabbing select-none"
    >
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={stableGraphData}
        backgroundColor={canvasBg}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, (node.val || 6) + 4, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
        linkColor={getLinkColor}
        linkWidth={getLinkWidth}
        linkLineDash={getLinkLineDash}
        linkDirectionalParticles={getLinkParticles}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleWidth={3}
        linkDirectionalParticleColor={() => "#FDE68A"}
        onNodeHover={(node: any) => setHoverNode(node || null)}
        onNodeClick={(node: any) => onSelectNode(node)}
        onNodeRightClick={(node: any, event: MouseEvent) => {
          event.preventDefault();
          setContextMenu({
            node,
            position: { x: event.clientX, y: event.clientY },
          });
        }}
        onEngineStop={handleEngineStop}
        onRenderFramePre={handleRenderFramePre}
        cooldownTicks={120}
        d3VelocityDecay={0.4}
      />

      {/* Right-click Context Menu */}
      {contextMenu && (
        <NodeContextMenu
          node={contextMenu.node}
          position={contextMenu.position}
          onClose={() => setContextMenu(null)}
          onExpandNeighbors={handleExpandNeighbors}
          onFindPathFromHere={handleFindPathFromHere}
          onHideNode={handleHideNode}
          onPinNode={handlePinNode}
        />
      )}
    </div>
  );
}

import { useRef, useEffect, useState, useMemo } from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import { UnrealBloomPass } from "three-stdlib";
import * as THREE from "three";
import { GraphLink, GraphNode } from "../types/graph";

export interface GraphCanvas3DProps {
  nodes: GraphNode[];
  links: GraphLink[];
  colorBy: "type" | "tier";
  selectedNodeId: string | null;
  onSelectNode: (node: GraphNode) => void;
  activePath: string[] | null;
  highlightedPathNodes: Set<string>;
  zoomToTrigger: number;
}

const TYPE_COLORS: Record<string, string> = {
  mechanism: "#F59E0B",
  database: "#38BDF8",
  person: "#8B5CF6",
  team: "#8B5CF6",
  service: "#10B981",
  document: "#38BDF8",
  query: "#F472B6",
  entity: "#8B5CF6",
};

const TIER_COLORS: Record<number, string> = {
  1: "#38BDF8",
  2: "#10B981",
  3: "#F59E0B",
};

export function GraphCanvas3D({
  nodes,
  links,
  colorBy,
  selectedNodeId,
  onSelectNode,
  activePath,
  highlightedPathNodes,
  zoomToTrigger,
}: GraphCanvas3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  // ResizeObserver
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

  // Configure UnrealBloomPass on the post-processing composer
  useEffect(() => {
    if (!fgRef.current) return;

    try {
      const composer = (fgRef.current as any).postProcessingComposer();
      if (composer) {
        const res = new THREE.Vector2(dimensions.width, dimensions.height);
        const bloomPass = new UnrealBloomPass(res, 1.5, 0.6, 0.1);
        composer.addPass(bloomPass);
      }
    } catch {
      // Graceful fallback
    }
  }, [dimensions]);

  // Slow auto-rotation when idle
  useEffect(() => {
    if (!fgRef.current || prefersReducedMotion) return;

    const controls = (fgRef.current as any).controls();
    if (controls) {
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.5;

      const stopRotate = () => {
        controls.autoRotate = false;
      };

      controls.addEventListener("start", stopRotate);
      return () => {
        controls.removeEventListener("start", stopRotate);
      };
    }
  }, [prefersReducedMotion]);

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

  // Fit view trigger
  useEffect(() => {
    if (zoomToTrigger > 0 && fgRef.current) {
      fgRef.current.zoomToFit(prefersReducedMotion ? 0 : 800, 30);
    }
  }, [zoomToTrigger, prefersReducedMotion]);

  // Focus on selected node
  useEffect(() => {
    if (selectedNodeId && fgRef.current) {
      const n = nodes.find((node) => node.id === selectedNodeId);
      if (n && (n as any).x !== undefined && (n as any).y !== undefined && (n as any).z !== undefined) {
        const distance = 160;
        const distRatio = 1 + distance / Math.hypot((n as any).x, (n as any).y, (n as any).z || 1);
        fgRef.current.cameraPosition(
          {
            x: (n as any).x * distRatio,
            y: (n as any).y * distRatio,
            z: (n as any).z * distRatio,
          },
          { x: (n as any).x, y: (n as any).y, z: (n as any).z },
          prefersReducedMotion ? 0 : 800
        );
      }
    }
  }, [selectedNodeId, nodes, prefersReducedMotion]);

  const getNodeColor = (node: GraphNode): string => {
    if (highlightedPathNodes.has(node.id)) return "#F59E0B";
    if (colorBy === "tier") return TIER_COLORS[node.tier || 1] || "#38BDF8";
    return TYPE_COLORS[node.type] || "#8B5CF6";
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full bg-[#09090b] rounded-none overflow-hidden cursor-grab active:cursor-grabbing select-none"
    >
      <ForceGraph3D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={{ nodes: [...nodes], links: [...links] }}
        backgroundColor="#09090b"
        nodeLabel={(n: any) => `${n.name} (${n.type})`}
        nodeColor={getNodeColor as any}
        nodeVal={(n: any) => (n.id === selectedNodeId ? 14 : n.val || 6)}
        nodeResolution={16}
        linkColor={(link: any) => {
          const srcId = typeof link.source === "object" ? link.source.id : link.source;
          const tgtId = typeof link.target === "object" ? link.target.id : link.target;
          const isPath = activePathLinkKeys.has(`${srcId}->${tgtId}`);
          return isPath ? "#F59E0B" : "rgba(255, 255, 255, 0.15)";
        }}
        linkWidth={(link: any) => {
          const srcId = typeof link.source === "object" ? link.source.id : link.source;
          const tgtId = typeof link.target === "object" ? link.target.id : link.target;
          return activePathLinkKeys.has(`${srcId}->${tgtId}`) ? 2.5 : 0.8;
        }}
        linkDirectionalParticles={(link: any) => {
          if (prefersReducedMotion) return 0;
          const srcId = typeof link.source === "object" ? link.source.id : link.source;
          const tgtId = typeof link.target === "object" ? link.target.id : link.target;
          return activePathLinkKeys.has(`${srcId}->${tgtId}`) ? 4 : 0;
        }}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleWidth={2.5}
        linkDirectionalParticleColor={() => "#FDE68A"}
        onNodeClick={(node: any) => onSelectNode(node)}
        cooldownTicks={120}
      />
    </div>
  );
}

export default GraphCanvas3D;

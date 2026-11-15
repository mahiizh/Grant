import * as Comlink from "comlink";
import Graph from "graphology";
import { bidirectional } from "graphology-shortest-path";
import pagerank from "graphology-metrics/centrality/pagerank";
import louvain from "graphology-communities-louvain";
import { GraphData, GraphNode, GraphLink } from "../types/graph";

export interface EnrichedNodeWorker extends GraphNode {
  cluster: number;
  clusterName: string;
  degree: number;
  inDegree: number;
  outDegree: number;
  pageRank: number;
  val: number;
}

export interface WorkerAnalyticsResult {
  nodes: EnrichedNodeWorker[];
  links: GraphLink[];
  clusters: { id: number; name: string; count: number; color: string }[];
  stats: {
    totalEntities: number;
    totalRelationships: number;
    clustersDetected: number;
    avgPathDepth: number;
    avgDegree: number;
  };
}

const CLUSTER_PALETTE = [
  { name: "Storage & Ingestion Hub", color: "#38BDF8" },
  { name: "Payments & Fraud Gateway", color: "#10B981" },
  { name: "Core Banking & Ledger", color: "#F59E0B" },
  { name: "SRE & Reliability Platform", color: "#8B5CF6" },
  { name: "Security & Governance", color: "#EC4899" },
  { name: "Event & Async Processing", color: "#06B6D4" },
];

export const analyticsWorkerApi = {
  computeAnalytics(data: GraphData): WorkerAnalyticsResult {
    const g = new Graph({ multi: false, type: "directed" });

    data.nodes.forEach((node) => {
      if (!g.hasNode(node.id)) {
        g.addNode(node.id, { ...node });
      }
    });

    data.links.forEach((link) => {
      const s = typeof link.source === "object" ? (link.source as any).id : link.source;
      const t = typeof link.target === "object" ? (link.target as any).id : link.target;
      if (g.hasNode(s) && g.hasNode(t)) {
        if (!g.hasEdge(s, t)) {
          g.addEdge(s, t, { relation: link.relation });
        }
      }
    });

    // PageRank
    let prScores: Record<string, number> = {};
    try {
      prScores = pagerank(g, { alpha: 0.85, maxIterations: 100, getEdgeWeight: () => 1 });
    } catch {
      data.nodes.forEach((n) => {
        prScores[n.id] = 1 / (data.nodes.length || 1);
      });
    }

    const prValues = Object.values(prScores);
    const maxPr = Math.max(...prValues, 0.001);
    const minPr = Math.min(...prValues, 0.0001);

    // Louvain Communities
    let communities: Record<string, number> = {};
    try {
      const undir = new Graph({ type: "undirected" });
      data.nodes.forEach((n) => undir.addNode(n.id));
      data.links.forEach((l) => {
        const s = typeof l.source === "object" ? (l.source as any).id : l.source;
        const t = typeof l.target === "object" ? (l.target as any).id : l.target;
        if (undir.hasNode(s) && undir.hasNode(t) && !undir.hasEdge(s, t)) {
          undir.addEdge(s, t);
        }
      });
      communities = louvain(undir);
    } catch {
      data.nodes.forEach((n, idx) => {
        communities[n.id] = idx % 4;
      });
    }

    // Enrich Nodes
    const enrichedNodes: EnrichedNodeWorker[] = data.nodes.map((node) => {
      const rawPr = prScores[node.id] ?? 0.01;
      const normalizedPr = (rawPr - minPr) / (maxPr - minPr || 1);
      const clusterId = communities[node.id] ?? 0;
      const clusterMeta = CLUSTER_PALETTE[clusterId % CLUSTER_PALETTE.length];

      const degree = g.hasNode(node.id) ? g.degree(node.id) : 0;
      const inDegree = g.hasNode(node.id) ? g.inDegree(node.id) : 0;
      const outDegree = g.hasNode(node.id) ? g.outDegree(node.id) : 0;
      const radius = 4 + normalizedPr * 12;

      return {
        ...node,
        cluster: clusterId,
        clusterName: clusterMeta.name,
        degree,
        inDegree,
        outDegree,
        pageRank: rawPr,
        val: radius,
      };
    });

    // Clusters Summary
    const clusterMap = new Map<number, { count: number; name: string; color: string }>();
    enrichedNodes.forEach((node) => {
      const cid = node.cluster;
      const meta = CLUSTER_PALETTE[cid % CLUSTER_PALETTE.length];
      if (!clusterMap.has(cid)) {
        clusterMap.set(cid, { count: 0, name: meta.name, color: meta.color });
      }
      clusterMap.get(cid)!.count += 1;
    });

    const clusters = Array.from(clusterMap.entries()).map(([id, info]) => ({
      id,
      name: info.name,
      count: info.count,
      color: info.color,
    }));

    // Stats
    const totalEntities = enrichedNodes.length;
    const totalRelationships = data.links.length;
    const clustersDetected = clusters.length;
    const avgDegree = totalEntities > 0 ? (totalRelationships * 2) / totalEntities : 0;

    let totalPathLength = 0;
    let pathsSampled = 0;
    const sampleNodes = enrichedNodes.slice(0, 10);
    for (let i = 0; i < sampleNodes.length; i++) {
      for (let j = i + 1; j < sampleNodes.length; j++) {
        try {
          const path = bidirectional(g, sampleNodes[i].id, sampleNodes[j].id);
          if (path && path.length > 1) {
            totalPathLength += path.length - 1;
            pathsSampled += 1;
          }
        } catch {
          // ignore disconnected
        }
      }
    }
    const avgPathDepth = pathsSampled > 0 ? totalPathLength / pathsSampled : 0;

    return {
      nodes: enrichedNodes,
      links: data.links,
      clusters,
      stats: {
        totalEntities,
        totalRelationships,
        clustersDetected,
        avgPathDepth,
        avgDegree,
      },
    };
  },

  findShortestPath(data: GraphData, sourceId: string, targetId: string): string[] | null {
    const g = new Graph({ multi: false, type: "directed" });
    data.nodes.forEach((node) => {
      if (!g.hasNode(node.id)) g.addNode(node.id);
    });
    data.links.forEach((l) => {
      const s = typeof l.source === "object" ? (l.source as any).id : l.source;
      const t = typeof l.target === "object" ? (l.target as any).id : l.target;
      if (g.hasNode(s) && g.hasNode(t) && !g.hasEdge(s, t)) {
        g.addEdge(s, t);
      }
    });

    try {
      return bidirectional(g, sourceId, targetId);
    } catch {
      return null;
    }
  },
};

Comlink.expose(analyticsWorkerApi);

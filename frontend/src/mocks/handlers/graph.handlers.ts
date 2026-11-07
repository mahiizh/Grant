import { http, HttpResponse } from "msw";
import { INITIAL_GRAPH_NODES, INITIAL_GRAPH_LINKS } from "../fixtures/graph.fixture";

let nodes = [...INITIAL_GRAPH_NODES];
let links = [...INITIAL_GRAPH_LINKS];

export function resetGraphMock() {
  nodes = [...INITIAL_GRAPH_NODES];
  links = [...INITIAL_GRAPH_LINKS];
}

export function deleteNodeFromGraphMock(nodeId: string) {
  nodes = nodes.filter((n) => n.id !== nodeId);
  links = links.filter((l) => l.source !== nodeId && l.target !== nodeId);
}

export const graphHandlers = [
  http.get("*/graph", ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") || 100);
    const asOf = url.searchParams.get("as_of");

    // Filter nodes if as_of is provided
    let filteredNodes = nodes;
    let filteredLinks = links;

    if (asOf) {
      filteredNodes = nodes.filter((n) => n.valid_from <= asOf && (!n.valid_to || n.valid_to >= asOf));
      const activeIds = new Set(filteredNodes.map((n) => n.id));
      filteredLinks = links.filter(
        (l) => activeIds.has(l.source) && activeIds.has(l.target) && l.valid_from <= asOf && (!l.valid_to || l.valid_to >= asOf)
      );
    }

    return HttpResponse.json({
      nodes: filteredNodes.slice(0, limit),
      links: filteredLinks.slice(0, limit * 2),
      total_nodes: filteredNodes.length,
      total_links: filteredLinks.length,
    });
  }),

  http.get("*/graph/nodes/:id/neighbors", ({ params, request }) => {
    const nodeId = String(params.id);
    const url = new URL(request.url);
    const depth = Number(url.searchParams.get("depth") || 1);

    const visited = new Set<string>([nodeId]);
    let currentFrontier = [nodeId];

    for (let d = 0; d < depth; d++) {
      const nextFrontier: string[] = [];
      for (const curr of currentFrontier) {
        for (const link of links) {
          if (link.source === curr && !visited.has(link.target)) {
            visited.add(link.target);
            nextFrontier.push(link.target);
          } else if (link.target === curr && !visited.has(link.source)) {
            visited.add(link.source);
            nextFrontier.push(link.source);
          }
        }
      }
      currentFrontier = nextFrontier;
    }

    const subNodes = nodes.filter((n) => visited.has(n.id));
    const subLinks = links.filter((l) => visited.has(l.source) && visited.has(l.target));

    return HttpResponse.json({
      center_node_id: nodeId,
      depth,
      nodes: subNodes,
      links: subLinks,
    });
  }),

  http.get("*/graph/path", ({ request }) => {
    const url = new URL(request.url);
    const fromNode = url.searchParams.get("from");
    const toNode = url.searchParams.get("to");

    if (!fromNode || !toNode) {
      return HttpResponse.json({ from_node: "", to_node: "", found: false, hops: 0, path: [], links: [] });
    }

    // Bidirectional BFS
    const queue: Array<{ curr: string; path: string[] }> = [{ curr: fromNode, path: [fromNode] }];
    const visited = new Set<string>([fromNode]);
    let foundPath: string[] = [];

    while (queue.length > 0) {
      const { curr, path } = queue.shift()!;
      if (curr === toNode) {
        foundPath = path;
        break;
      }
      for (const link of links) {
        const neighbor = link.source === curr ? link.target : link.target === curr ? link.source : null;
        if (neighbor && !visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push({ curr: neighbor, path: [...path, neighbor] });
        }
      }
    }

    if (foundPath.length > 0) {
      const pathLinks = links.filter((l) => {
        for (let i = 0; i < foundPath.length - 1; i++) {
          if (
            (l.source === foundPath[i] && l.target === foundPath[i + 1]) ||
            (l.target === foundPath[i] && l.source === foundPath[i + 1])
          ) {
            return true;
          }
        }
        return false;
      });

      return HttpResponse.json({
        from_node: fromNode,
        to_node: toNode,
        found: true,
        path: foundPath,
        hops: foundPath.length - 1,
        links: pathLinks,
      });
    }

    return HttpResponse.json({
      from_node: fromNode,
      to_node: toNode,
      found: false,
      hops: 0,
      path: [],
      links: [],
    });
  }),
];

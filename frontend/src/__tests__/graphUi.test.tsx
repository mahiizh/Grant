import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { UseQueryResult } from "@tanstack/react-query";
import type { GraphChunkText, GraphNode, GraphQueryDetail } from "../types/graph";

vi.mock("../lib/api/hooks/useGraph", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api/hooks/useGraph")>();
  return {
    ...actual,
    useEntityChunks: vi.fn(),
    useQueryDetail: vi.fn(),
  };
});

import { NodeInspectorPanel } from "../features/NodeInspectorPanel";
import { useEntityChunks, useQueryDetail } from "../lib/api/hooks/useGraph";

const entityNode: GraphNode = {
  id: "ent-1",
  name: "Aurora Key",
  type: "entity",
  node_kind: "entity",
  description: "Aurora Key",
  source_kind: "document",
  source_kinds: ["document"],
  degree: 2,
  tier: 1,
};

const queryNode: GraphNode = {
  id: "qry-1",
  name: "What protects the gateway?",
  type: "query",
  node_kind: "query",
  description: "What protects the gateway?",
  source_kind: "chat",
  source_kinds: ["chat"],
  degree: 1,
  tier: 1,
};

const queryDetail: GraphQueryDetail = {
  query_id: "qry-1",
  query: "What protects the gateway?",
  rewritten_query: null,
  answer: "Aurora Key protects the gateway.",
  source: "docs",
  path: ["docs", "web"],
  top_score: 0.87,
  answer_policy: "grounded_plus_web",
  created_at: null,
};

function queryResult<T>(data: T): UseQueryResult<T, Error> {
  return { data, isLoading: false, error: null } as unknown as UseQueryResult<T, Error>;
}

const chunks: GraphChunkText[] = [
  {
    chunk_id: "chk-1",
    doc_id: "doc-1",
    text: "Aurora Key protects the Data Platform Team gateway.",
    source_kind: "document",
    title: "Platform runbook",
    url: null,
    mention_count: 3,
  },
  {
    chunk_id: "chk-2",
    doc_id: "doc-2",
    text: "Qdrant stores the gateway evidence.",
    source_kind: "web",
    title: "Web note",
    url: "https://example.com",
    mention_count: 1,
  },
];

describe("Step 7 Graph UI inspector", () => {
  beforeEach(() => {
    vi.mocked(useEntityChunks).mockReturnValue(queryResult<GraphChunkText[]>([]));
    vi.mocked(useQueryDetail).mockReturnValue(queryResult<GraphQueryDetail | null>(null));
  });

  it("shows query answer, source and path on a Query node click", () => {
    vi.mocked(useQueryDetail).mockReturnValue(queryResult(queryDetail));

    render(
      <NodeInspectorPanel
        node={queryNode}
        nodes={[queryNode]}
        links={[]}
        onSelectNode={() => {}}
        onFindPath={() => {}}
      />
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Answer" }), { button: 0 });
    expect(screen.getByText("Aurora Key protects the gateway.")).toBeTruthy();
    expect(screen.getByText("docs → web")).toBeTruthy();
    expect(screen.getByText("0.870")).toBeTruthy();
    expect(screen.getAllByText("query").length).toBeGreaterThan(0);
  });

  it("shows Postgres-mention chunk texts on an Entity node click", () => {
    vi.mocked(useEntityChunks).mockReturnValue(queryResult(chunks));

    render(
      <NodeInspectorPanel
        node={entityNode}
        nodes={[entityNode]}
        links={[]}
        onSelectNode={() => {}}
        onFindPath={() => {}}
      />
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Chunk Texts (2)" }), { button: 0 });
    expect(screen.getByText("Aurora Key protects the Data Platform Team gateway.")).toBeTruthy();
    expect(screen.getByText("Qdrant stores the gateway evidence.")).toBeTruthy();
    expect(screen.getByText("Platform runbook")).toBeTruthy();
    expect(screen.getByText("×3")).toBeTruthy();
  });

  it("keeps entity-only path controls away from Document/Query nodes", () => {
    render(
      <NodeInspectorPanel
        node={queryNode}
        nodes={[queryNode]}
        links={[]}
        onSelectNode={() => {}}
        onFindPath={() => {}}
      />
    );
    expect(screen.queryByText("Find path to entity...")).toBeNull();
  });
});

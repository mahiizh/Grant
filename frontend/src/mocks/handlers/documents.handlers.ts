import { http, HttpResponse } from "msw";
import { INITIAL_DOCS_FIXTURE, DocumentFixture } from "../fixtures/docs.fixture";

let documents: DocumentFixture[] = [...INITIAL_DOCS_FIXTURE];

export function resetDocumentsMock() {
  documents = [...INITIAL_DOCS_FIXTURE];
}

export const documentsHandlers = [
  http.get("*/documents", () => {
    return HttpResponse.json({
      documents,
      total: documents.length,
    });
  }),

  http.post("*/documents", async () => {
    const newDocId = `doc-${Date.now()}`;
    const newDoc: DocumentFixture = {
      id: newDocId,
      title: "newly-uploaded-architecture.md",
      file_type: "md",
      size_kb: 42,
      chunks: 8,
      entities_extracted: 6,
      relations_extracted: 10,
      tier: 1,
      ingested_at: new Date().toISOString().replace("T", " ").substring(0, 16),
      target_node_id: "postgres",
      valid_from: new Date().toISOString().substring(0, 10),
    };

    documents.unshift(newDoc);

    return HttpResponse.json({
      document_id: newDocId,
      title: newDoc.title,
      status: "ingesting",
      message: "Document ingestion pipeline started",
    });
  }),

  http.delete("*/documents/:id", ({ params }) => {
    const docId = String(params.id);
    const exists = documents.some((d) => d.id === docId);

    if (!exists) {
      return new HttpResponse(JSON.stringify({ detail: "Document not found" }), { status: 404 });
    }

    documents = documents.filter((d) => d.id !== docId);

    return HttpResponse.json({
      document_id: docId,
      success: true,
      stores_cleared: ["PostgreSQL", "Qdrant", "Neo4j", "Redis"],
    });
  }),

  http.get("*/documents/:id/impact", ({ params }) => {
    const docId = String(params.id);
    const doc = documents.find((d) => d.id === docId) || INITIAL_DOCS_FIXTURE[0];

    return HttpResponse.json({
      document_id: docId,
      affected_entities: [doc.target_node_id, "postgres", "data_platform"],
      affected_relations: ["STAGED_IN", "OWNED_BY", "LED_BY"],
      affected_chunks: Array.from({ length: doc.chunks }, (_, i) => `${docId}-chunk-${i + 1}`),
      blast_radius_score: 0.42,
    });
  }),

  http.get("*/documents/:id/status", ({ params, request }) => {
    const docId = String(params.id);
    const accept = request.headers.get("accept");

    if (accept && accept.includes("text/event-stream")) {
      // SSE Stream progressing through 4 stages over ~6s
      const encoder = new TextEncoder();
      const stages = [
        { status: "parsing", active_step: "Chunking & Parsing document", step_index: 1, entities: 0, relations: 0 },
        { status: "embedding", active_step: "Generating 3072d Qdrant dense vectors", step_index: 2, entities: 2, relations: 1 },
        { status: "extracting", active_step: "Extracting entity relationships via LLM", step_index: 3, entities: 8, relations: 11 },
        { status: "completed", active_step: "Bi-temporal Neo4j indexing completed", step_index: 4, entities: 8, relations: 12 },
      ];

      const stream = new ReadableStream({
        async start(controller) {
          for (const st of stages) {
            const data = JSON.stringify({ id: docId, ...st, total_steps: 4 });
            controller.enqueue(encoder.encode(`event: status\ndata: ${data}\n\n`));
            await new Promise((r) => setTimeout(r, 1500));
          }
          controller.close();
        },
      });

      return new HttpResponse(stream, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
      });
    }

    // Polling fallback
    return HttpResponse.json({
      id: docId,
      status: "completed",
      active_step: "Ingestion and indexing complete",
      step_index: 4,
      total_steps: 4,
      entities: 8,
      relations: 12,
    });
  }),
];

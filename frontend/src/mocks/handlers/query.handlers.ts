import { http, HttpResponse } from "msw";
import { GOLDEN_SET_FIXTURE } from "../fixtures/evals.fixture";
import { MOCK_CHUNKS_FIXTURE } from "../fixtures/chunks.fixture";

export const queryHandlers = [
  http.post("*/query", async ({ request }) => {
    let body: any = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }

    const queryText = (body.query || "").trim();
    const queryLower = queryText.toLowerCase();

    // Check if matching an unanswerable question or category
    const unanswerableMatch = GOLDEN_SET_FIXTURE.find(
      (g) =>
        g.category === "unanswerable" &&
        (queryLower.includes(g.question.toLowerCase().substring(0, 20)) ||
          g.question.toLowerCase().includes(queryLower))
    );

    const isAbstention =
      Boolean(unanswerableMatch) ||
      queryLower.includes("bypass") ||
      queryLower.includes("phone number") ||
      queryLower.includes("password") ||
      queryLower.includes("stock price") ||
      queryLower.includes("2029") ||
      queryLower.includes("2035") ||
      queryLower.includes("confidential medical");

    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        function sendEvent(type: string, data: any) {
          controller.enqueue(encoder.encode(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`));
        }

        if (isAbstention) {
          sendEvent("stage", { stage: "route", detail: "Abstention Gate", status: "completed" });
          await new Promise((r) => setTimeout(r, 100));

          sendEvent("stage", { stage: "check", detail: "Boundary Evaluation Gate: Abstention Triggered", status: "warning" });
          await new Promise((r) => setTimeout(r, 100));

          const abstentionMessage =
            unanswerableMatch?.expected_answer ||
            "I cannot answer this query based on the verified documents in the knowledge base. Grant Lab strictly enforces grounding boundaries and refrains from hallucinating or answering out-of-domain requests.";

          const words = abstentionMessage.split(" ");
          for (const word of words) {
            sendEvent("token", { token: word + " " });
            await new Promise((r) => setTimeout(r, 20));
          }

          sendEvent("done", {
            query: queryText,
            answer: abstentionMessage,
            strategy_used: "abstention",
            is_cached: false,
            is_abstention: true,
            evidence: [],
            path: [],
            cost_usd: 0.0002,
            latency_ms: 180,
          });

          controller.close();
          return;
        }

        // Standard Grounded Answer Workflow
        sendEvent("stage", { stage: "route", detail: "Hybrid Search (conf 0.91)", status: "completed" });
        await new Promise((r) => setTimeout(r, 120));

        sendEvent("stage", { stage: "cache", detail: "Redis Semantic Cache Miss (0.64 < 0.92)", status: "completed" });
        await new Promise((r) => setTimeout(r, 100));

        sendEvent("stage", { stage: "retrieve", detail: "Qdrant (14 chunks) + Neo4j (2 hops)", status: "completed" });
        await new Promise((r) => setTimeout(r, 150));

        sendEvent("stage", { stage: "fuse", detail: "RRF Fusion Engine (k=60)", status: "completed" });
        await new Promise((r) => setTimeout(r, 80));

        sendEvent("stage", { stage: "rerank", detail: "ms-marco Cross-Encoder Top 5", status: "completed" });
        await new Promise((r) => setTimeout(r, 120));

        sendEvent("stage", { stage: "check", detail: "Faithfulness 0.96 (all claims verified)", status: "completed" });
        await new Promise((r) => setTimeout(r, 90));

        sendEvent("stage", { stage: "generate", detail: "claude-3-5-sonnet streaming response", status: "completed" });

        // Stream Citations
        sendEvent("citations", {
          chunks: MOCK_CHUNKS_FIXTURE,
        });

        const fullAnswer =
          "The transactional outbox service experienced replication stalls due to row-level lock escalation on PostgreSQL table outbox_events [1]. The background polling daemon was starved of connections because the connection pool limit was saturated by concurrent reporting jobs.\n\nAlice Chen's Data Platform squad diagnosed the bottleneck and remediated the stall by deploying a PgBouncer transaction-pooler configuration update and enabling bi-temporal CDC ingestion into Qdrant [2]. In addition, eventual consistency with the Neo4j bi-temporal graph was recovered by replaying the uncommitted events from the Dead-Letter Queue (DLQ) [3].";

        const words = fullAnswer.split(" ");
        for (const word of words) {
          sendEvent("token", { token: word + " " });
          await new Promise((r) => setTimeout(r, 15));
        }

        sendEvent("done", {
          query: queryText,
          answer: fullAnswer,
          strategy_used: "hybrid_search",
          is_cached: false,
          is_abstention: false,
          evidence: MOCK_CHUNKS_FIXTURE.map((c) => ({
            chunk_id: c.chunkId,
            doc_id: c.file,
            text: c.snippet,
            score: c.score,
            retrieval_method: "rrf",
            path: c.nodeIds,
          })),
          path: ["outbox", "postgres", "data_platform", "alice_chen", "neo4j"],
          cost_usd: 0.0031,
          latency_ms: 618,
        });

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
  }),
];

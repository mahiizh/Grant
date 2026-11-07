import { http, HttpResponse } from "msw";
import { MOCK_CHUNKS_FIXTURE } from "../fixtures/chunks.fixture";

interface MockCitation {
  chunk_id: string;
  doc_id: string;
  text: string;
  score: number;
  retrieval_method: string;
  path?: string[] | null;
}

interface MockMessage {
  message_id: string;
  thread_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  raw_query?: string | null;
  rewritten_query?: string | null;
  route?: string | null;
  cache_status?: string | null;
  latency_ms?: number | null;
  cost_usd?: number | null;
  tokens?: number | null;
  trace_id?: string | null;
  citations: MockCitation[];
  pipeline_stages: any[];
  subgraph_nodes: string[];
  feedback?: "up" | "down" | null;
  feedback_note?: string | null;
  generations: any[];
  created_at: string;
}

interface MockThread {
  thread_id: string;
  title: string;
  acl_scope: string;
  as_of_date?: string | null;
  created_at: string;
  updated_at: string;
  messages: MockMessage[];
}

const now = new Date();
const todayIso = now.toISOString();
const yesterdayIso = new Date(now.getTime() - 86400000).toISOString();
const olderIso = new Date(now.getTime() - 86400000 * 3).toISOString();

const MOCK_THREADS_STORE: MockThread[] = [
  {
    thread_id: "th-demo-outbox-01",
    title: "Transactional Outbox & PostgreSQL Replication Stall",
    acl_scope: "data-platform",
    as_of_date: "2026-04-12",
    created_at: todayIso,
    updated_at: todayIso,
    messages: [
      {
        message_id: "msg-001-u",
        thread_id: "th-demo-outbox-01",
        role: "user",
        content: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
        raw_query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
        rewritten_query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
        citations: [],
        pipeline_stages: [],
        subgraph_nodes: [],
        generations: [],
        created_at: todayIso,
      },
      {
        message_id: "msg-001-a",
        thread_id: "th-demo-outbox-01",
        role: "assistant",
        content:
          "The transactional outbox service experienced replication stalls due to row-level lock escalation on PostgreSQL table outbox_events [1]. The background polling daemon was starved of connections because the connection pool limit was saturated by concurrent reporting jobs.\n\nAlice Chen's Data Platform squad diagnosed the bottleneck and remediated the stall by deploying a PgBouncer transaction-pooler configuration update and enabling bi-temporal CDC ingestion into Qdrant [2]. In addition, eventual consistency with the Neo4j bi-temporal graph was recovered by replaying the uncommitted events from the Dead-Letter Queue (DLQ) [3].",
        raw_query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
        rewritten_query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
        route: "hybrid",
        cache_status: "miss",
        latency_ms: 618,
        cost_usd: 0.0031,
        tokens: 340,
        trace_id: "tr-outbox-001",
        citations: MOCK_CHUNKS_FIXTURE.map((c) => ({
          chunk_id: c.chunkId,
          doc_id: c.file,
          text: c.snippet,
          score: c.score,
          retrieval_method: "rrf",
          path: c.nodeIds,
        })),
        pipeline_stages: [
          { id: "condense", label: "Condense query", status: "completed", duration_ms: 12, detail: "Standalone verified" },
          { id: "route", label: "Route (hybrid)", status: "completed", duration_ms: 14, detail: "Hybrid 0.91" },
          { id: "cache", label: "Cache check", status: "completed", duration_ms: 6, detail: "Miss 0.64" },
          { id: "retrieve", label: "Retrieve evidence", status: "completed", duration_ms: 52, detail: "14 chunks" },
          { id: "fuse", label: "RRF fuse", status: "completed", duration_ms: 3, detail: "RRF k=60" },
          { id: "rerank", label: "Cross-encoder rerank", status: "completed", duration_ms: 92, detail: "Top 3 chunks" },
          { id: "synthesize", label: "Synthesize answer", status: "completed", duration_ms: 420, detail: "340 tokens" },
        ],
        subgraph_nodes: ["outbox", "postgres", "dlq", "alice_chen"],
        feedback: "up",
        feedback_note: "Accurate incident details",
        generations: [],
        created_at: todayIso,
      },
      {
        message_id: "msg-002-u",
        thread_id: "th-demo-outbox-01",
        role: "user",
        content: "How did they fix it?",
        raw_query: "How did they fix it?",
        citations: [],
        pipeline_stages: [],
        subgraph_nodes: [],
        generations: [],
        created_at: todayIso,
      },
      {
        message_id: "msg-002-a",
        thread_id: "th-demo-outbox-01",
        role: "assistant",
        content:
          "Alice Chen's Data Platform squad upgraded PostgreSQL 16 to utilize PgBouncer in transaction-pooling mode [1]. They configured valid_from and valid_to payload intervals synchronized with Qdrant [2] to isolate point-in-time state, and drained the DLQ dead-letter backlog directly into Neo4j [3].",
        raw_query: "How did they fix it?",
        rewritten_query: "How did Alice Chen's Data Platform squad fix the outbox service replication stall on PostgreSQL?",
        route: "hybrid",
        cache_status: "miss",
        latency_ms: 450,
        cost_usd: 0.0024,
        tokens: 280,
        trace_id: "tr-outbox-002",
        citations: MOCK_CHUNKS_FIXTURE.slice(0, 2).map((c) => ({
          chunk_id: c.chunkId,
          doc_id: c.file,
          text: c.snippet,
          score: c.score,
          retrieval_method: "vector",
          path: c.nodeIds,
        })),
        pipeline_stages: [
          { id: "condense", label: "Condense query", status: "completed", duration_ms: 18, detail: "Resolved 'they' -> Alice Chen, 'it' -> outbox" },
          { id: "route", label: "Route (vector)", status: "completed", duration_ms: 10, detail: "Vector 0.88" },
          { id: "cache", label: "Cache check", status: "completed", duration_ms: 5, detail: "Miss" },
          { id: "retrieve", label: "Retrieve evidence", status: "completed", duration_ms: 45, detail: "6 chunks" },
          { id: "synthesize", label: "Synthesize answer", status: "completed", duration_ms: 360, detail: "280 tokens" },
        ],
        subgraph_nodes: ["alice_chen", "data_platform", "qdrant"],
        feedback: null,
        generations: [],
        created_at: todayIso,
      },
    ],
  },
  {
    thread_id: "th-demo-bitemporal-02",
    title: "Bi-Temporal Contract Verification",
    acl_scope: "payments",
    as_of_date: "2026-03-01",
    created_at: yesterdayIso,
    updated_at: yesterdayIso,
    messages: [
      {
        message_id: "msg-003-u",
        thread_id: "th-demo-bitemporal-02",
        role: "user",
        content: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
        raw_query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
        rewritten_query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
        citations: [],
        pipeline_stages: [],
        subgraph_nodes: [],
        generations: [],
        created_at: yesterdayIso,
      },
      {
        message_id: "msg-003-a",
        thread_id: "th-demo-bitemporal-02",
        role: "assistant",
        content:
          "On 2026-03-01, SLA contract v1.2 was active across all core banking and payment gateway endpoints [1]. The schema migration to bi-temporal interval logging was not committed until 2026-03-15 [2].",
        raw_query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
        rewritten_query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
        route: "graph",
        cache_status: "miss",
        latency_ms: 520,
        cost_usd: 0.0028,
        tokens: 220,
        trace_id: "tr-bitemp-001",
        citations: [
          {
            chunk_id: "chunk-sla-01",
            doc_id: "docs/contracts/sla-2026.md",
            text: "SLA contract v1.2 active valid_from 2026-01-01 valid_to 2026-03-15.",
            score: 0.95,
            retrieval_method: "graph_traversal",
            path: ["sla_v1", "core_banking"],
          },
        ],
        pipeline_stages: [
          { id: "condense", label: "Condense query", status: "completed", duration_ms: 10, detail: "Standalone query" },
          { id: "route", label: "Route (graph)", status: "completed", duration_ms: 12, detail: "Graph 0.94" },
          { id: "retrieve", label: "Neo4j traversal", status: "completed", duration_ms: 60, detail: "Temporal filter active" },
          { id: "synthesize", label: "Synthesize answer", status: "completed", duration_ms: 380, detail: "220 tokens" },
        ],
        subgraph_nodes: ["sla_v1", "core_banking"],
        feedback: null,
        generations: [],
        created_at: yesterdayIso,
      },
    ],
  },
  {
    thread_id: "th-demo-cache-03",
    title: "Cache Invalidation Blast Radius",
    acl_scope: "sre",
    as_of_date: null,
    created_at: olderIso,
    updated_at: olderIso,
    messages: [
      {
        message_id: "msg-004-u",
        thread_id: "th-demo-cache-03",
        role: "user",
        content: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
        raw_query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
        rewritten_query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
        citations: [],
        pipeline_stages: [],
        subgraph_nodes: [],
        generations: [],
        created_at: olderIso,
      },
      {
        message_id: "msg-004-a",
        thread_id: "th-demo-cache-03",
        role: "assistant",
        content:
          "If Redis node 3 fails, the cluster initiates automatic Sentinel failover within 800ms [1]. During failover, queries bypass the semantic cache and fall back directly to Qdrant dense retrieval, raising p95 latency from 18ms to approximately 65ms [2].",
        raw_query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
        rewritten_query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
        route: "hybrid",
        cache_status: "miss",
        latency_ms: 380,
        cost_usd: 0.002,
        tokens: 190,
        trace_id: "tr-cache-001",
        citations: [
          {
            chunk_id: "chunk-redis-failover",
            doc_id: "docs/runbooks/redis-sentinel.md",
            text: "Redis Sentinel quorum failover executes within 800ms; vector store absorbs fallback load.",
            score: 0.93,
            retrieval_method: "hybrid",
            path: ["redis_node_3", "sentinel", "qdrant"],
          },
        ],
        pipeline_stages: [
          { id: "condense", label: "Condense query", status: "completed", duration_ms: 8, detail: "Standalone" },
          { id: "route", label: "Route (hybrid)", status: "completed", duration_ms: 11, detail: "Hybrid" },
          { id: "retrieve", label: "Retrieve evidence", status: "completed", duration_ms: 40, detail: "4 chunks" },
          { id: "synthesize", label: "Synthesize answer", status: "completed", duration_ms: 300, detail: "190 tokens" },
        ],
        subgraph_nodes: ["redis_node_3", "sentinel", "qdrant"],
        feedback: "up",
        feedback_note: null,
        generations: [],
        created_at: olderIso,
      },
    ],
  },
];

export const threadsHandlers = [
  // List threads
  http.get("*/threads", () => {
    const summaries = MOCK_THREADS_STORE.map((th) => ({
      thread_id: th.thread_id,
      title: th.title,
      acl_scope: th.acl_scope,
      as_of_date: th.as_of_date,
      created_at: th.created_at,
      updated_at: th.updated_at,
      message_count: th.messages.length,
      preview: th.messages[th.messages.length - 1]?.content.slice(0, 80) || null,
    })).sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

    return HttpResponse.json(summaries);
  }),

  // Create thread
  http.post("*/threads", async ({ request }) => {
    let body: any = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }

    const thread_id = `th-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const newThread: MockThread = {
      thread_id,
      title: body.title || "New Investigation",
      acl_scope: body.acl_scope || "data-platform",
      as_of_date: body.as_of_date || null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [],
    };
    MOCK_THREADS_STORE.unshift(newThread);

    return HttpResponse.json(newThread, { status: 201 });
  }),

  // Get thread
  http.get("*/threads/:id", ({ params }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }
    return HttpResponse.json(thread);
  }),

  // Patch thread
  http.patch("*/threads/:id", async ({ params, request }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }

    const body: any = await request.json();
    if (body.title !== undefined) thread.title = body.title;
    if (body.acl_scope !== undefined) thread.acl_scope = body.acl_scope;
    if (body.as_of_date !== undefined) thread.as_of_date = body.as_of_date;
    thread.updated_at = new Date().toISOString();

    return HttpResponse.json(thread);
  }),

  // Delete thread
  http.delete("*/threads/:id", ({ params }) => {
    const idx = MOCK_THREADS_STORE.findIndex((t) => t.thread_id === params.id);
    if (idx === -1) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }
    MOCK_THREADS_STORE.splice(idx, 1);
    return HttpResponse.json({ deleted: true, thread_id: params.id });
  }),

  // Send message with SSE
  http.post("*/threads/:id/messages", async ({ params, request }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }

    const body: any = await request.json();
    const query = (body.content || "").trim();
    const queryLower = query.toLowerCase();

    // Mid-thread scope or date updates
    if (body.acl_scope && body.acl_scope !== thread.acl_scope) {
      thread.acl_scope = body.acl_scope;
    }
    if (body.as_of_date && body.as_of_date !== thread.as_of_date) {
      thread.as_of_date = body.as_of_date;
    }

    // Auto title
    if (thread.title === "New Investigation" && thread.messages.length === 0) {
      thread.title = query.slice(0, 45) + (query.length > 45 ? "..." : "");
    }

    const nowIso = new Date().toISOString();
    thread.updated_at = nowIso;

    // Add user message
    const userMsgId = `msg-${Date.now().toString(36)}-u`;
    const userMsg: MockMessage = {
      message_id: userMsgId,
      thread_id: thread.thread_id,
      role: "user",
      content: query,
      raw_query: query,
      rewritten_query: query,
      citations: [],
      pipeline_stages: [],
      subgraph_nodes: [],
      generations: [],
      created_at: nowIso,
    };
    thread.messages.push(userMsg);

    // Pronoun resolution simulation
    let rewritten = query;
    if (queryLower.includes("they") || queryLower.includes("it") || queryLower.includes("how did they fix it")) {
      rewritten = "How did Alice Chen's Data Platform squad fix the outbox service replication stall on PostgreSQL?";
    } else if (queryLower.includes("who commanded") || queryLower.includes("who was commanding that")) {
      rewritten = "Who was incident commander for incident INC-2026-04?";
    }

    const citations: MockCitation[] = MOCK_CHUNKS_FIXTURE.map((c) => ({
      chunk_id: c.chunkId,
      doc_id: c.file,
      text: c.snippet,
      score: c.score,
      retrieval_method: "rrf",
      path: c.nodeIds,
    }));

    const stages = [
      { id: "condense", label: "Condense query", status: "completed", duration_ms: 15, detail: `Standalone: '${rewritten}'` },
      { id: "route", label: "Route (hybrid)", status: "completed", duration_ms: 12, detail: "Hybrid 0.91" },
      { id: "cache", label: "Cache check", status: "completed", duration_ms: 6, detail: "Miss 0.64" },
      { id: "retrieve", label: "Retrieve evidence", status: "completed", duration_ms: 48, detail: "14 chunks" },
      { id: "fuse", label: "RRF fuse", status: "completed", duration_ms: 3, detail: "RRF k=60" },
      { id: "rerank", label: "Cross-encoder rerank", status: "completed", duration_ms: 88, detail: "Top 3 chunks" },
      { id: "synthesize", label: "Synthesize answer", status: "completed", duration_ms: 380, detail: "310 tokens" },
    ];

    const answer = queryLower.includes("fix")
      ? "Alice Chen's Data Platform squad upgraded PostgreSQL 16 to utilize PgBouncer in transaction-pooling mode [1]. They configured valid_from and valid_to intervals into Qdrant [2] to enforce state isolation, and recovered Neo4j bi-temporal graph consistency by replaying uncommitted events from the Dead-Letter Queue (DLQ) [3]."
      : `Based on verified documents in the knowledge base, the ${rewritten.replace(/\?$/, "")} was resolved through coordinated infrastructure updates [1]. PostgreSQL connection pooling was adjusted [2] and bi-temporal state was resynchronized across Qdrant and Neo4j [3].`;

    const asstMsgId = `msg-${Date.now().toString(36)}-a`;
    const asstMsg: MockMessage = {
      message_id: asstMsgId,
      thread_id: thread.thread_id,
      role: "assistant",
      content: answer,
      raw_query: query,
      rewritten_query: rewritten,
      route: "hybrid",
      cache_status: "miss",
      latency_ms: 552,
      cost_usd: 0.0028,
      tokens: 310,
      trace_id: `tr-${Math.random().toString(36).slice(2, 10)}`,
      citations,
      pipeline_stages: stages,
      subgraph_nodes: ["outbox", "postgres", "data_platform", "alice_chen"],
      feedback: null,
      generations: [],
      created_at: new Date().toISOString(),
    };
    thread.messages.push(asstMsg);

    // Return SSE stream
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        function send(event: string, data: any) {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        }

        send("stage", { id: "condense", label: "Condensing query", status: "in_progress" });
        await new Promise((r) => setTimeout(r, 60));

        send("rewrite", { raw_query: query, rewritten_query: rewritten });
        send("stage", stages[0]);
        await new Promise((r) => setTimeout(r, 50));

        send("stage", stages[1]);
        await new Promise((r) => setTimeout(r, 50));

        send("stage", stages[2]);
        await new Promise((r) => setTimeout(r, 50));

        send("stage", stages[3]);
        await new Promise((r) => setTimeout(r, 60));

        const words = answer.split(" ");
        for (const word of words) {
          send("token", { token: word + " " });
          await new Promise((r) => setTimeout(r, 12));
        }

        send("stage", stages[6]);
        send("citations", citations);
        send("done", asstMsg);
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

  // Feedback 👍/👎
  http.post("*/threads/:id/messages/:msgId/feedback", async ({ params, request }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }
    const msg = thread.messages.find((m) => m.message_id === params.msgId);
    if (!msg) {
      return new HttpResponse(null, { status: 404, statusText: "Message not found" });
    }

    const body: any = await request.json();
    msg.feedback = body.feedback;
    msg.feedback_note = body.note || null;

    return HttpResponse.json(msg);
  }),

  // Add to golden set
  http.post("*/threads/:id/messages/:msgId/golden", async ({ params }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }
    const msg = thread.messages.find((m) => m.message_id === params.msgId);
    if (!msg) {
      return new HttpResponse(null, { status: 404, statusText: "Message not found" });
    }

    const candidateId = `eval_candidate_${Math.random().toString(36).slice(2, 10)}`;
    return HttpResponse.json({
      status: "added",
      golden_id: candidateId,
      file: "golden_candidates.jsonl",
    });
  }),

  // Regenerate message
  http.post("*/threads/:id/messages/:msgId/regenerate", ({ params }) => {
    const thread = MOCK_THREADS_STORE.find((t) => t.thread_id === params.id);
    if (!thread) {
      return new HttpResponse(null, { status: 404, statusText: "Thread not found" });
    }
    const msg = thread.messages.find((m) => m.message_id === params.msgId);
    if (!msg) {
      return new HttpResponse(null, { status: 404, statusText: "Message not found" });
    }

    // Archive current generation
    msg.generations = msg.generations || [];
    msg.generations.push({
      generation_id: `gen-${msg.generations.length + 1}`,
      content: msg.content,
      rewritten_query: msg.rewritten_query,
      route: msg.route,
      cache_status: msg.cache_status,
      latency_ms: msg.latency_ms,
      cost_usd: msg.cost_usd,
      tokens: msg.tokens,
      trace_id: msg.trace_id,
      citations: msg.citations,
      created_at: msg.created_at,
    });

    // Update with fresh answer
    msg.content = `[Regenerated variation] ${msg.content}`;
    msg.latency_ms = (msg.latency_ms || 400) + 25;
    msg.trace_id = `tr-regen-${Math.random().toString(36).slice(2, 8)}`;
    msg.created_at = new Date().toISOString();

    return HttpResponse.json(msg);
  }),
];

import { http, HttpResponse } from "msw";
import { TRACES_DATA_FIXTURE } from "../fixtures/traces.fixture";

let traces = [...TRACES_DATA_FIXTURE];

export function resetTracesMock() {
  traces = [...TRACES_DATA_FIXTURE];
}

export const tracesHandlers = [
  http.get("*/traces", ({ request }) => {
    const url = new URL(request.url);
    const route = url.searchParams.get("route");
    const minLatency = Number(url.searchParams.get("min_latency") || 0);
    const status = url.searchParams.get("status");

    let filtered = traces;

    if (route && route !== "all") {
      filtered = filtered.filter((t) => t.route === route);
    }
    if (minLatency > 0) {
      filtered = filtered.filter((t) => t.totalDurationMs >= minLatency);
    }
    if (status && status !== "all") {
      filtered = filtered.filter((t) => t.status === status);
    }

    const summaries = filtered.map((t) => ({
      id: t.id,
      query: t.query,
      route: t.route,
      latency_ms: t.totalDurationMs,
      status: t.status,
      timestamp: t.timestamp,
      tokens: t.totalTokens,
      cost_usd: t.costUsd,
      cached: t.cacheStatus === "hit",
      error_message: null,
    }));

    return HttpResponse.json({
      traces: summaries,
      total: summaries.length,
    });
  }),

  http.get("*/traces/:id", ({ params }) => {
    const traceId = String(params.id);
    const trace = traces.find((t) => t.id === traceId) || traces[0];

    return HttpResponse.json({
      id: trace.id,
      query: trace.query,
      route: trace.route,
      latency_ms: trace.totalDurationMs,
      status: trace.status,
      timestamp: trace.timestamp,
      tokens: trace.totalTokens,
      cost_usd: trace.costUsd,
      spans: trace.spans.map((s) => ({
        name: s.name,
        service: s.lane,
        start_ms: s.startMs,
        duration_ms: s.durationMs,
        status: s.status,
        meta: Object.entries(s.attributes)
          .map(([k, v]) => `${k}=${v}`)
          .join(", "),
      })),
      inputs: { query: trace.query },
      retrieved_chunk_ids: ["chunk-4", "chunk-12", "chunk-9"],
      answer: "Synthetic verified trace execution details.",
    });
  }),
];

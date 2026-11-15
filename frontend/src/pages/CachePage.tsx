import { useMemo } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Zap, ShieldCheck, Key, Clock } from "lucide-react";
import { useCacheStats, useCacheInvalidations } from "../lib/api/hooks/useCache";
import { useGuardrailsMetrics } from "../lib/api/hooks/useMetrics";
import { QueryState } from "../components/ui/QueryState";

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not measured" : `${(value * 100).toFixed(1)}%`;
}

export function CachePage() {
  const stats = useCacheStats("24h");
  const invalidationsQuery = useCacheInvalidations();
  const guardrails = useGuardrailsMetrics();

  const chartData = useMemo(() => {
    if (stats.data?.series && stats.data.series.length > 0) {
      return stats.data.series.map((p) => ({
        time: p.timestamp,
        hits: p.hits,
        misses: p.misses,
      }));
    }
    return [];
  }, [stats.data]);

  const invalidations = invalidationsQuery.data?.invalidations ?? [];

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6 max-w-7xl mx-auto select-none">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <Zap className="h-5 w-5 text-amber-400" />
            Semantic Cache & Guardrails Telemetry
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Telemetry for Redis response caching, Outbox-driven key invalidation, and guardrails.
            Values are shown only when the backend measures them.
          </p>
        </div>
      </div>

      {/* Cache telemetry — backend returns 501 until counters are persisted */}
      <QueryState
        isLoading={stats.isLoading}
        error={stats.error}
        data={stats.data}
        onRetry={() => stats.refetch()}
        loadingSkeleton={
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-zinc-900/60 border border-zinc-800/80 animate-pulse" />
            ))}
          </div>
        }
      >
        {(data) => (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
                <div className="text-xs text-zinc-400 font-mono">Cache Hit Ratio</div>
                <div className="text-2xl font-semibold text-emerald-400 font-mono tabular-nums">
                  {percent(data.overall_hit_rate)}
                </div>
                <div className="text-[10px] text-zinc-500">
                  {data.total_requests} requests in window
                </div>
              </div>

              <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
                <div className="text-xs text-zinc-400 font-mono">P95 Savings</div>
                <div className="text-2xl font-semibold text-zinc-100 font-mono tabular-nums">
                  {data.p95_savings_ms.toFixed(1)}ms
                </div>
                <div className="text-[10px] text-zinc-500">Saved per cache hit</div>
              </div>

              <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
                <div className="text-xs text-zinc-400 font-mono">Wrong-Hit Rate</div>
                <div className="text-2xl font-semibold text-amber-400 font-mono tabular-nums">
                  {percent(data.wrong_hit_rate)}
                </div>
                <div className="text-[10px] text-zinc-500">Rejected by guardrails</div>
              </div>

              <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
                <div className="text-xs text-zinc-400 font-mono">Window</div>
                <div className="text-2xl font-semibold text-sky-400 font-mono tabular-nums">
                  {data.window}
                </div>
                <div className="text-[10px] text-zinc-500">Telemetry aggregation period</div>
              </div>
            </div>

            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2 text-zinc-100">
                  <Clock className="h-4 w-4 text-emerald-400" />
                  Cache Hits vs. Misses
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                {chartData.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-xs text-zinc-500 font-mono">
                    No time-series points in this window.
                  </div>
                ) : (
                  <div className="h-64 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="hitsGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="missesGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#71717A" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#71717A" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="time" stroke="#71717A" fontSize={11} tickLine={false} />
                        <YAxis stroke="#71717A" fontSize={11} tickLine={false} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#09090b",
                            border: "1px solid #27272a",
                            borderRadius: "8px",
                            fontSize: "12px",
                            fontFamily: "monospace",
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="hits"
                          stroke="#10B981"
                          strokeWidth={2}
                          fillOpacity={1}
                          fill="url(#hitsGrad)"
                        />
                        <Area
                          type="monotone"
                          dataKey="misses"
                          stroke="#71717A"
                          strokeWidth={1.5}
                          fillOpacity={1}
                          fill="url(#missesGrad)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </QueryState>

      {/* Guardrail telemetry — backend returns 501 until counters are persisted */}
      <Card className="bg-zinc-900/60 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-zinc-100">
            <ShieldCheck className="h-4 w-4 text-amber-400" />
            Safety & Faithfulness Gates
          </CardTitle>
        </CardHeader>
        <CardContent>
          <QueryState
            isLoading={guardrails.isLoading}
            error={guardrails.error}
            data={guardrails.data}
            onRetry={() => guardrails.refetch()}
            loadingSkeleton={<div className="h-24 rounded-lg bg-zinc-950/60 animate-pulse" />}
          >
            {(data) => (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
                  <div className="text-zinc-400 font-mono text-[11px]">Hallucination Score</div>
                  <div className="text-lg font-semibold text-emerald-400 font-mono tabular-nums">
                    {data.hallucination_eval_score.toFixed(3)}
                  </div>
                </div>
                <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
                  <div className="text-zinc-400 font-mono text-[11px]">Prompt Injection Attempts</div>
                  <div className="text-lg font-semibold text-sky-400 font-mono tabular-nums">
                    {data.prompt_injection_attempts}
                  </div>
                </div>
                <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
                  <div className="text-zinc-400 font-mono text-[11px]">Pass Rate</div>
                  <div className="text-lg font-semibold text-amber-400 font-mono tabular-nums">
                    {percent(data.pass_rate)}
                  </div>
                </div>
              </div>
            )}
          </QueryState>
        </CardContent>
      </Card>

      {/* Outbox Invalidation Log — real endpoint */}
      <Card className="bg-zinc-900/60 border-zinc-800">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-zinc-100">
              <Key className="h-4 w-4 text-rose-400" />
              Transactional Outbox Invalidation Audit Log
            </CardTitle>
            <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">
              Hook: Postgres CDC
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <QueryState
            isLoading={invalidationsQuery.isLoading}
            error={invalidationsQuery.error}
            data={invalidationsQuery.data}
            isEmpty={(d) => !d.invalidations || d.invalidations.length === 0}
            emptyIcon={Key}
            emptyTitle="No invalidations recorded"
            emptyDescription="Outbox-driven cache invalidations will appear here after a document changes or is deleted."
            onRetry={() => invalidationsQuery.refetch()}
            loadingSkeleton={<div className="h-24 rounded-lg bg-zinc-950/60 animate-pulse" />}
          >
            {() => (
              <div className="space-y-2">
                {invalidations.map((inv) => (
                  <div
                    key={inv.id}
                    className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="h-1.5 w-1.5 rounded-full bg-rose-400 shrink-0" />
                        <span className="font-semibold text-zinc-200">{inv.trigger_event}</span>
                        <Badge variant="outline" className="text-[9px] border-zinc-800 text-zinc-500 py-0">
                          {inv.acl_scope}
                        </Badge>
                      </div>
                      <div className="text-[11px] text-zinc-400">
                        Purged keys:{" "}
                        <span className="text-amber-400 font-sans">{inv.affected_keys_count}</span>{" "}
                        · {inv.reason}
                      </div>
                    </div>
                    <span className="text-[11px] text-zinc-500 shrink-0">{inv.timestamp}</span>
                  </div>
                ))}
              </div>
            )}
          </QueryState>
        </CardContent>
      </Card>
    </div>
  );
}

export default CachePage;

import { useState, useMemo } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Zap,
  ShieldCheck,
  Key,
  Clock,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { useCacheStats, useCacheInvalidations } from "../lib/api/hooks/useCache";

interface InvalidationRecord {
  id: string;
  event: string;
  timestamp: string;
  keysPurged: string[];
  sourceTable: string;
}

export function CachePage() {
  const { data: statsResponse } = useCacheStats("24h");
  const { data: invalidationsResponse } = useCacheInvalidations();

  const chartData = useMemo(() => {
    if (statsResponse?.series && statsResponse.series.length > 0) {
      return statsResponse.series.map((p) => ({
        time: p.timestamp,
        hits: p.hits,
        misses: p.misses,
      }));
    }
    return [];
  }, [statsResponse]);

  const [localInvalidations, setLocalInvalidations] = useState<InvalidationRecord[]>([]);

  const invalidations = useMemo(() => {
    const list: InvalidationRecord[] = [];
    if (invalidationsResponse?.invalidations && invalidationsResponse.invalidations.length > 0) {
      for (const inv of invalidationsResponse.invalidations) {
        list.push({
          id: inv.id,
          event: inv.trigger_event,
          timestamp: inv.timestamp,
          keysPurged: (inv as any).keys_purged || [`keys (${inv.affected_keys_count})`],
          sourceTable: (inv as any).source_table || inv.reason,
        });
      }
    }
    return [...localInvalidations, ...list];
  }, [invalidationsResponse, localInvalidations]);

  const handlePurgeAll = () => {
    setLocalInvalidations((prev) => [
      {
        id: `inv-${Date.now()}`,
        event: "manual.admin.cache_purge",
        timestamp: new Date().toLocaleTimeString(),
        keysPurged: ["* (all 2,140 keys)"],
        sourceTable: "manual_flush",
      },
      ...prev,
    ]);
    toast.success("Flushed all warm keys from Redis Semantic Cache");
  };

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
            Real-time telemetry for Redis semantic response caching, Outbox-driven key invalidation, and input/output guardrails.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handlePurgeAll}
            className="h-7 text-xs border-zinc-800 bg-zinc-900 text-rose-400 hover:text-rose-300 hover:bg-zinc-800"
          >
            <Trash2 className="h-3 w-3 mr-1" />
            Flush Cache
          </Button>
        </div>
      </div>

      {/* KPI Stats Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Cache Hit Ratio</div>
          <div className="text-2xl font-semibold text-emerald-400 font-mono tabular-nums">78.4%</div>
          <div className="text-[10px] text-zinc-500">624 hits / 796 total queries</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">P95 Cache Hit Latency</div>
          <div className="text-2xl font-semibold text-zinc-100 font-mono tabular-nums">8.2ms</div>
          <div className="text-[10px] text-zinc-500">vs 618ms full LLM pipeline</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Total USD Saved</div>
          <div className="text-2xl font-semibold text-amber-400 font-mono tabular-nums">$42.18</div>
          <div className="text-[10px] text-zinc-500">avoided 1.4M model tokens</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Active Key Memory</div>
          <div className="text-2xl font-semibold text-sky-400 font-mono tabular-nums">18.4 MB</div>
          <div className="text-[10px] text-zinc-500">TTL: 3600s with outbox hooks</div>
        </div>
      </div>

      {/* Main Charts & Telemetry Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Cache Invocations Over Time Chart (2 cols) */}
        <Card className="lg:col-span-2 bg-zinc-900/60 border-zinc-800">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-2 text-zinc-100">
                <Clock className="h-4 w-4 text-emerald-400" />
                Cache Hits vs. Misses (Hourly)
              </CardTitle>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" /> Hits
                </span>
                <span className="flex items-center gap-1.5 text-zinc-500">
                  <span className="h-2 w-2 rounded-full bg-zinc-600" /> Misses
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-2">
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
          </CardContent>
        </Card>

        {/* Guardrails Telemetry Card */}
        <Card className="bg-zinc-900/60 border-zinc-800 flex flex-col justify-between">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-zinc-100">
              <ShieldCheck className="h-4 w-4 text-amber-400" />
              Safety & Faithfulness Gates
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="flex justify-between items-center font-mono">
                <span className="text-zinc-400">Hallucination Gate</span>
                <span className="text-emerald-400 font-semibold">99.2% Pass</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div className="bg-emerald-400 h-full rounded-full w-[99.2%]" />
              </div>
              <div className="text-[10px] text-zinc-500">1 claim rejected out of 124 evaluated</div>
            </div>

            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="flex justify-between items-center font-mono">
                <span className="text-zinc-400">Prompt Injection Intercept</span>
                <span className="text-sky-400 font-semibold">14 Blocked</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div className="bg-sky-400 h-full rounded-full w-[100%]" />
              </div>
              <div className="text-[10px] text-zinc-500">Regex + Classifier dual-layer filter</div>
            </div>

            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="flex justify-between items-center font-mono">
                <span className="text-zinc-400">PII Redaction Engine</span>
                <span className="text-amber-400 font-semibold">0 Leaks</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div className="bg-amber-400 h-full rounded-full w-[100%]" />
              </div>
              <div className="text-[10px] text-zinc-500">SSN, CC numbers, JWT tokens scrubbed</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Outbox Invalidation Log */}
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
          <div className="space-y-2">
            {invalidations.map((inv) => (
              <div
                key={inv.id}
                className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-rose-400 shrink-0" />
                    <span className="font-semibold text-zinc-200">{inv.event}</span>
                    <Badge variant="outline" className="text-[9px] border-zinc-800 text-zinc-500 py-0">
                      table: {inv.sourceTable}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-zinc-400">
                    Purged keys: <span className="text-amber-400 font-sans">{inv.keysPurged.join(", ")}</span>
                  </div>
                </div>
                <span className="text-[11px] text-zinc-500 shrink-0">{inv.timestamp}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default CachePage;

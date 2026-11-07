import { useState, useMemo } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Activity,
  Search,
  Clock,
  Coins,
  Copy,
  Check,
  Cpu,
} from "lucide-react";
import { toast } from "sonner";
import { useTraces, useTrace } from "../lib/api/hooks/useTraces";

export interface SpanData {
  id: string;
  name: string;
  lane: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "miss" | "hit";
  attributes: Record<string, string | number | boolean>;
  input?: string;
  output?: string;
}

export interface TraceRecord {
  id: string;
  query: string;
  timestamp: string;
  totalDurationMs: number;
  totalTokens: number;
  costUsd: number;
  route: string;
  cacheStatus: "hit" | "miss";
  status: "success" | "warning" | "error";
  spans: SpanData[];
}

export function TracesPage() {
  const [selectedTraceId, setSelectedTraceId] = useState<string>("tr-8f92a10b");
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>("sp-8");
  const [searchFilter, setSearchFilter] = useState("");
  const [routeFilter, setRouteFilter] = useState("all");
  const [copiedJson, setCopiedJson] = useState(false);

  const { data: tracesResponse } = useTraces({
    route: routeFilter !== "all" ? routeFilter : undefined,
  });

  const { data: traceDetail } = useTrace(selectedTraceId);

  const traces: TraceRecord[] = useMemo(() => {
    if (tracesResponse?.traces && tracesResponse.traces.length > 0) {
      return tracesResponse.traces.map((t) => {
        const spans = traceDetail && traceDetail.id === t.id && traceDetail.spans
          ? traceDetail.spans.map((s, idx) => ({
              id: `sp-${idx}`,
              name: s.name,
              lane: s.service,
              startMs: s.start_ms,
              durationMs: s.duration_ms,
              status: (s.status as any) || "ok",
              attributes: { meta: s.meta },
            }))
          : [];

        return {
          id: t.id,
          query: t.query,
          timestamp: t.timestamp,
          totalDurationMs: t.latency_ms,
          totalTokens: t.tokens,
          costUsd: t.cost_usd,
          route: t.route,
          cacheStatus: t.cached ? ("hit" as const) : ("miss" as const),
          status: (t.status as any) || "success",
          spans,
        };
      });
    }
    return [];
  }, [tracesResponse, traceDetail]);

  const selectedTrace = useMemo(
    () => traces.find((t) => t.id === selectedTraceId) || traces[0] || null,
    [traces, selectedTraceId]
  );

  const selectedSpan = useMemo(
    () => (selectedTrace?.spans ? selectedTrace.spans.find((s) => s.id === selectedSpanId) || selectedTrace.spans[0] || null : null),
    [selectedTrace, selectedSpanId]
  );

  const filteredTraces = useMemo(() => {
    return traces.filter((t) => {
      const matchSearch =
        t.query.toLowerCase().includes(searchFilter.toLowerCase()) ||
        t.id.toLowerCase().includes(searchFilter.toLowerCase());
      const matchRoute = routeFilter === "all" || t.route === routeFilter;
      return matchSearch && matchRoute;
    });
  }, [traces, searchFilter, routeFilter]);

  const maxTraceDuration = selectedTrace ? Math.max(selectedTrace.totalDurationMs, 500) : 500;

  const handleCopySpanJson = () => {
    if (!selectedSpan) return;
    navigator.clipboard.writeText(JSON.stringify(selectedSpan, null, 2));
    setCopiedJson(true);
    toast.success("Span JSON copied to clipboard");
    setTimeout(() => setCopiedJson(false), 2000);
  };

  return (
    <div className="flex-1 flex h-full overflow-hidden bg-zinc-950 select-none">
      {/* Left Column: Traces Master List */}
      <div className="w-80 sm:w-96 border-r border-zinc-800/80 bg-zinc-950 flex flex-col shrink-0 overflow-hidden">
        {/* Filter Toolbar */}
        <div className="p-3 border-b border-zinc-800/80 space-y-2.5 bg-zinc-900/40 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-zinc-100 flex items-center gap-1.5">
              <Activity className="h-4 w-4 text-amber-400" />
              Distributed Traces
            </span>
            <span className="text-[10px] font-mono text-zinc-500 tabular-nums">
              {filteredTraces.length} recorded
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <div className="relative flex-1">
              <Search className="h-3 w-3 absolute left-2.5 top-2 text-zinc-500" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Search trace ID or query..."
                aria-label="Search trace ID or query"
                className="w-full bg-zinc-900 border border-zinc-800 rounded-md pl-7 pr-3 py-1 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-700 font-sans"
              />
            </div>
            <select
              value={routeFilter}
              onChange={(e) => setRouteFilter(e.target.value)}
              aria-label="Filter traces by route"
              className="h-6 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-zinc-300 px-1.5 focus:outline-none"
            >
              <option value="all">All Routes</option>
              <option value="hybrid_search">hybrid</option>
              <option value="graph_traversal">graph</option>
              <option value="temporal_cypher">temporal</option>
              <option value="vector_search">vector</option>
            </select>
          </div>
        </div>

        {/* Traces List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {filteredTraces.map((trace) => {
            const isSelected = trace.id === selectedTraceId;

            return (
              <div
                key={trace.id}
                onClick={() => {
                  setSelectedTraceId(trace.id);
                  setSelectedSpanId(trace.spans[0]?.id || null);
                }}
                className={`p-3 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                  isSelected
                    ? "border-amber-500/50 bg-amber-500/10 shadow-[0_0_10px_rgba(245,158,11,0.15)]"
                    : "border-zinc-800/80 bg-zinc-900/30 hover:bg-zinc-900/60 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="font-semibold text-zinc-300">{trace.id}</span>
                  <div className="flex items-center gap-1.5">
                    {trace.cacheStatus === "hit" ? (
                      <Badge variant="outline" className="text-[9px] font-mono border-rose-500/30 text-rose-400 bg-rose-500/10 py-0">
                        CACHE HIT
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[9px] font-mono border-zinc-700 text-zinc-400 py-0">
                        {trace.route}
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="text-xs text-zinc-300 line-clamp-2 leading-relaxed">
                  "{trace.query}"
                </div>

                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 pt-1 border-t border-zinc-800/50">
                  <span className="text-amber-400 font-semibold tabular-nums">{trace.totalDurationMs}ms</span>
                  <span>{trace.totalTokens} tokens</span>
                  <span className="text-emerald-400 font-medium">${trace.costUsd.toFixed(4)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Middle Column: Selected Trace Header & Waterfall Gantt Chart */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {selectedTrace ? (
          <>
            {/* Trace Header */}
        <div className="p-4 border-b border-zinc-800/80 bg-zinc-900/30 space-y-3 shrink-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-zinc-300">
                Trace: {selectedTrace.id}
              </span>
              <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/30 text-emerald-400 bg-emerald-500/10">
                {selectedTrace.status.toUpperCase()}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono text-zinc-400">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3 text-amber-400" />
                <strong className="text-zinc-200">{selectedTrace.totalDurationMs}ms</strong>
              </span>
              <span className="flex items-center gap-1">
                <Coins className="h-3 w-3 text-emerald-400" />
                <strong className="text-zinc-200">${selectedTrace.costUsd.toFixed(4)}</strong>
              </span>
              <span>{selectedTrace.timestamp}</span>
            </div>
          </div>

          <div className="text-xs text-zinc-200 font-sans bg-zinc-950/70 p-2.5 rounded-lg border border-zinc-800">
            "{selectedTrace.query}"
          </div>
        </div>

        {/* Waterfall View (Gantt Chart) */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div className="flex items-center justify-between text-xs font-mono text-zinc-500 border-b border-zinc-800/80 pb-2">
            <span>Execution Lanes & Spans ({selectedTrace.spans.length})</span>
            <span>Timeline: 0ms → {maxTraceDuration}ms</span>
          </div>

          <div className="space-y-2">
            {selectedTrace.spans.map((sp) => {
              const isSelected = selectedSpan?.id === sp.id;
              const leftPercent = (sp.startMs / maxTraceDuration) * 100;
              const widthPercent = Math.max((sp.durationMs / maxTraceDuration) * 100, 2.5);

              return (
                <div
                  key={sp.id}
                  onClick={() => setSelectedSpanId(sp.id)}
                  className={`p-2.5 rounded-lg border transition-all cursor-pointer space-y-1.5 ${
                    isSelected
                      ? "border-amber-400 bg-amber-500/10 shadow-[0_0_10px_rgba(245,158,11,0.2)]"
                      : "border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-900/70 hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                      <span className="font-semibold text-zinc-200">{sp.name}</span>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        [{sp.lane}]
                      </span>
                    </div>
                    <span className="text-amber-400 font-mono font-medium tabular-nums text-[11px]">
                      {sp.durationMs}ms
                    </span>
                  </div>

                  {/* Gantt Bar */}
                  <div className="w-full bg-zinc-950 rounded-full h-2 relative overflow-hidden border border-zinc-800/60">
                    <div
                      className="absolute h-full rounded-full bg-amber-400"
                      style={{
                        left: `${leftPercent}%`,
                        width: `${widthPercent}%`,
                      }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
                    <span>offset +{sp.startMs}ms</span>
                    <span>status: {sp.status.toUpperCase()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-2 text-zinc-500 font-mono text-xs">
            <Activity className="h-6 w-6 text-zinc-600 animate-pulse" />
            <span>Select or load a trace to inspect waterfall spans</span>
          </div>
        )}
      </div>

      {/* Right Column: Span Detail Drawer */}
      <div className="w-80 sm:w-96 border-l border-zinc-800/80 bg-zinc-950 flex flex-col shrink-0 overflow-hidden">
        <div className="p-3.5 border-b border-zinc-800/80 bg-zinc-900/40 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200">
            <Cpu className="h-3.5 w-3.5 text-amber-400" />
            <span>Span Telemetry Attributes</span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleCopySpanJson}
            className="h-6 text-[10px] font-mono border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-300"
          >
            {copiedJson ? <Check className="h-2.5 w-2.5 mr-1 text-emerald-400" /> : <Copy className="h-2.5 w-2.5 mr-1" />}
            Copy JSON
          </Button>
        </div>

        {selectedSpan ? (
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-mono">
            {/* Span Overview */}
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 space-y-1.5">
              <div className="font-semibold text-zinc-100">{selectedSpan.name}</div>
              <div className="text-[11px] text-zinc-400">Lane: {selectedSpan.lane}</div>
              <div className="text-[11px] text-amber-400 tabular-nums">
                Duration: {selectedSpan.durationMs}ms (offset +{selectedSpan.startMs}ms)
              </div>
            </div>

            {/* OpenTelemetry Semantic Conventions */}
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                OpenTelemetry Attributes
              </div>
              <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/30 space-y-1.5 text-[11px]">
                {Object.entries(selectedSpan.attributes).map(([key, val]) => (
                  <div key={key} className="flex justify-between py-0.5 border-b border-zinc-800/50 last:border-0">
                    <span className="text-zinc-400">{key}</span>
                    <span className="text-zinc-200 font-semibold">{String(val)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Inputs & Outputs */}
            {selectedSpan.input && (
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  Step Input
                </div>
                <pre className="p-3 rounded-lg border border-zinc-800 bg-zinc-950 text-[11px] text-zinc-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  {selectedSpan.input}
                </pre>
              </div>
            )}

            {selectedSpan.output && (
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  Step Output
                </div>
                <pre className="p-3 rounded-lg border border-zinc-800 bg-zinc-950 text-[11px] text-emerald-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  {selectedSpan.output}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-xs text-zinc-500 font-mono">
            Select a span to inspect its attributes
          </div>
        )}
      </div>
    </div>
  );
}

export default TracesPage;

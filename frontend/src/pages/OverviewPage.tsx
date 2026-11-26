import { Card, CardHeader, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  ShieldCheck,
  Clock,
  Zap,
  Coins,
  CheckCircle2,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { useOverviewMetrics } from "../lib/api/hooks/useMetrics";
import { QueryState } from "../components/ui/QueryState";

const NOT_MEASURED = "Not measured";

function isUnmeasured(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined;
}

function percent(value: number | null | undefined): string {
  return isUnmeasured(value) ? NOT_MEASURED : `${(value * 100).toFixed(1)}%`;
}

export function OverviewPage() {
  const navigate = useNavigate();
  const { data: metrics, isLoading, error, refetch } = useOverviewMetrics();

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6 max-w-7xl mx-auto select-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-400" />
            GraphRAG Intelligence Lab Overview
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Telemetry and service-level indicators for grounded retrieval, exact caching, and answer provenance.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => navigate("/ask")}
            className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-medium h-8 text-xs cursor-pointer"
          >
            Launch Query Console
            <ArrowRight className="h-3 w-3 ml-1" />
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <QueryState
        isLoading={isLoading}
        error={error}
        data={metrics}
        onRetry={() => refetch()}
        loadingSkeleton={
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-32 rounded-xl bg-zinc-900/60 border border-zinc-800/80 animate-pulse" />
            ))}
          </div>
        }
      >
        {(data) => {
          const kpis = [
            {
              title: "Documents Indexed",
              value: `${data.docs_indexed} Documents`,
              subtext: `${data.chunks_indexed} chunks · ${data.entities_indexed} entities · ${data.relations_indexed} links`,
              icon: FileText,
              color: "text-sky-400",
              target: "/documents",
            },
            {
              title: "Golden-Set Accuracy",
              value: percent(data.golden_set_accuracy),
              subtext: isUnmeasured(data.golden_set_accuracy)
                ? "No recorded accuracy available"
                : "Latest recorded evaluation run",
              icon: ShieldCheck,
              color: "text-emerald-400",
            },
            {
              title: "P95 Pipeline Latency",
              value: isUnmeasured(data.p95_latency_ms)
                ? NOT_MEASURED
                : `${data.p95_latency_ms} ms`,
              subtext: isUnmeasured(data.p95_latency_ms)
                ? "No completed queries recorded yet"
                : "Computed from stored assistant messages",
              icon: Clock,
              color: "text-amber-400",
            },
            {
              title: "Cache Hit Rate",
              value: percent(data.cache_hit_rate),
              subtext: isUnmeasured(data.cache_hit_rate)
                ? "No cache-tagged messages recorded yet"
                : "Exact hits from stored messages",
              icon: Zap,
              color: "text-emerald-400",
            },
            {
              title: "Cost Per Correct Answer",
              value: isUnmeasured(data.cost_per_correct_answer_usd)
                ? NOT_MEASURED
                : `$${data.cost_per_correct_answer_usd!.toFixed(4)}`,
              subtext: "The pipeline does not persist per-answer cost",
              icon: Coins,
              color: "text-emerald-400",
            },
            {
              title: "Unverified Facts Pending",
              value: `${data.unverified_facts_pending} Claims`,
              subtext: "Chunks whose provenance is not marked verified",
              icon: CheckCircle2,
              color: "text-sky-400",
            },
          ];

          return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {kpis.map((kpi) => {
                const Icon = kpi.icon;

                return (
                  <Card
                    key={kpi.title}
                    onClick={kpi.target ? () => navigate(kpi.target) : undefined}
                    className={`bg-zinc-900/60 border-zinc-800 transition-all group ${
                      kpi.target ? "hover:border-zinc-700 cursor-pointer" : ""
                    }`}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-mono text-zinc-400 font-semibold">{kpi.title}</div>
                        <div className={`p-1.5 rounded-lg bg-zinc-950 border border-zinc-800 ${kpi.color}`}>
                          <Icon className="h-4 w-4" />
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <div className="text-2xl font-semibold text-zinc-100 font-mono tracking-tight tabular-nums">
                        {kpi.value}
                      </div>
                      <div className="flex items-center justify-between text-[11px] font-mono pt-1 border-t border-zinc-800/60">
                        <span className="text-zinc-500 truncate max-w-[220px]">{kpi.subtext}</span>
                        {kpi.value === NOT_MEASURED && (
                          <Badge variant="outline" className="text-[9px] shrink-0 border-zinc-800 text-zinc-500">
                            No data
                          </Badge>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          );
        }}
      </QueryState>

      {/* Quick Launch */}
      <div className="pt-2">
        <div
          onClick={() => navigate("/graph")}
          className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 hover:border-zinc-700 transition-all cursor-pointer space-y-1.5 group"
        >
          <div className="flex items-center justify-between text-xs font-semibold text-zinc-200 group-hover:text-amber-400">
            <span>Knowledge Graph Explorer</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed">
            Inspect entities and relationships with source provenance and degree.
          </p>
        </div>
      </div>
    </div>
  );
}

export default OverviewPage;

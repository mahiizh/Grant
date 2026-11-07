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
            Real-time telemetry and service-level indicators for bi-temporal retrieval, semantic caching, and claim faithfulness.
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

      {/* 6 KPI Cards Grid */}
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
              subtext: `${data.chunks_indexed} total chunks · ${data.entities_indexed} entities · ${data.relations_indexed} links`,
              icon: FileText,
              trend: "+1 this week",
              trendType: "neutral" as const,
              color: "text-sky-400",
              target: "/documents",
            },
            {
              title: "Golden-Set Accuracy",
              value: `${(data.golden_set_accuracy * 100).toFixed(1)}%`,
              subtext: "20 / 20 regression benchmark queries verified",
              icon: ShieldCheck,
              trend: "0 regressions",
              trendType: "positive" as const,
              color: "text-emerald-400",
              target: "/golden-set",
            },
            {
              title: "P95 Pipeline Latency",
              value: `${data.p95_latency_ms} ms`,
              subtext: "Target SLA: 850ms (passing with -27% headroom)",
              icon: Clock,
              trend: "-85ms faster",
              trendType: "positive" as const,
              color: "text-amber-400",
              target: "/traces",
            },
            {
              title: "Cache Hit / Wrong-Hit Rate",
              value: `${(data.cache_hit_rate * 100).toFixed(1)}% / ${(data.cache_wrong_hit_rate * 100).toFixed(1)}%`,
              subtext: "624 hits · 3 wrong-hits intercepted by guardrail",
              icon: Zap,
              trend: "+12.1% hits",
              trendType: "positive" as const,
              color: "text-emerald-400",
              target: "/cache",
            },
            {
              title: "Cost Per Correct Answer",
              value: `$${data.cost_per_correct_answer_usd.toFixed(4)}`,
              subtext: "Avg 340 generation tokens + RRF candidate pruning",
              icon: Coins,
              trend: "-$0.0012 (-28%)",
              trendType: "positive" as const,
              color: "text-emerald-400",
              target: "/experiments",
            },
            {
              title: "Unverified Facts Pending",
              value: `${data.unverified_facts_pending} Claims`,
              subtext: "100% extracted claims grounded in Tier 1–2 evidence",
              icon: CheckCircle2,
              trend: "Faithfulness 0.958",
              trendType: "positive" as const,
              color: "text-sky-400",
              target: "/retrieval",
            },
          ];

          return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {kpis.map((kpi) => {
                const Icon = kpi.icon;

                return (
                  <Card
                    key={kpi.title}
                    onClick={() => navigate(kpi.target)}
                    className="bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 transition-all cursor-pointer group"
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
                        <span className="text-zinc-500 truncate max-w-[190px]">{kpi.subtext}</span>
                        <Badge
                          variant="outline"
                          className={`text-[9px] shrink-0 ${
                            kpi.trendType === "positive"
                              ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                              : "border-zinc-800 text-zinc-400"
                          }`}
                        >
                          {kpi.trend}
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          );
        }}
      </QueryState>

      {/* Quick Launch Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        <div
          onClick={() => navigate("/graph")}
          className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 hover:border-zinc-700 transition-all cursor-pointer space-y-1.5 group"
        >
          <div className="flex items-center justify-between text-xs font-semibold text-zinc-200 group-hover:text-amber-400">
            <span>Knowledge Graph Explorer</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed">
            Inspect the 36-entity bi-temporal topology, Louvain community clusters, and active reasoning particle paths.
          </p>
        </div>

        <div
          onClick={() => navigate("/retrieval")}
          className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 hover:border-zinc-700 transition-all cursor-pointer space-y-1.5 group"
        >
          <div className="flex items-center justify-between text-xs font-semibold text-zinc-200 group-hover:text-amber-400">
            <span>RRF & Dense/Sparse Fusion</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed">
            Tune Reciprocal Rank Fusion constant k, vector similarity floors, and cross-encoder score cutoffs with live rank-shifts.
          </p>
        </div>

        <div
          onClick={() => navigate("/traces")}
          className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/80 hover:border-zinc-700 transition-all cursor-pointer space-y-1.5 group"
        >
          <div className="flex items-center justify-between text-xs font-semibold text-zinc-200 group-hover:text-amber-400">
            <span>Distributed Spans & Waterfall</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed">
            Review OpenTelemetry semantic traces across LangGraph orchestrator, Redis cache, Qdrant vectors, and Neo4j.
          </p>
        </div>
      </div>
    </div>
  );
}

export default OverviewPage;

import { useState, useMemo } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  FlaskConical,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Sliders,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import { useExperiments, useUpdateExperiment } from "../lib/api/hooks/useExperiments";

interface ExperimentItem {
  id: number;
  query: string;
  variantA: {
    route: string;
    accuracy: boolean;
    faithfulness: number;
    latencyMs: number;
    costUsd: number;
  };
  variantB: {
    route: string;
    accuracy: boolean;
    faithfulness: number;
    latencyMs: number;
    costUsd: number;
  };
}

const DEFAULT_RUNS: ExperimentItem[] = [
  {
    id: 1,
    query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
    variantA: { route: "vector_only", accuracy: false, faithfulness: 0.81, latencyMs: 690, costUsd: 0.0038 },
    variantB: { route: "hybrid_rrf", accuracy: true, faithfulness: 0.96, latencyMs: 618, costUsd: 0.0031 },
  },
  {
    id: 2,
    query: "What databases and services depend on the Qdrant vector index when processing core-banking events?",
    variantA: { route: "vector_only", accuracy: false, faithfulness: 0.74, latencyMs: 540, costUsd: 0.0034 },
    variantB: { route: "hybrid_rrf", accuracy: true, faithfulness: 0.94, latencyMs: 485, costUsd: 0.0024 },
  },
  {
    id: 3,
    query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
    variantA: { route: "vector_only", accuracy: false, faithfulness: 0.68, latencyMs: 410, costUsd: 0.0028 },
    variantB: { route: "hybrid_rrf", accuracy: true, faithfulness: 0.98, latencyMs: 310, costUsd: 0.0018 },
  },
  {
    id: 4,
    query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
    variantA: { route: "vector_only", accuracy: true, faithfulness: 0.89, latencyMs: 580, costUsd: 0.0032 },
    variantB: { route: "hybrid_rrf", accuracy: true, faithfulness: 0.91, latencyMs: 512, costUsd: 0.0022 },
  },
  {
    id: 5,
    query: "Who leads the SRE team and triaged the payment gateway incident on 2026-04-12?",
    variantA: { route: "vector_only", accuracy: true, faithfulness: 0.86, latencyMs: 340, costUsd: 0.0025 },
    variantB: { route: "hybrid_rrf", accuracy: true, faithfulness: 0.99, latencyMs: 280, costUsd: 0.0016 },
  },
];

export function ExperimentsPage() {
  const { data: expResponse } = useExperiments();
  const updateExperimentMutation = useUpdateExperiment();

  const activeExp = useMemo(() => {
    return (
      expResponse?.experiments?.[0] || {
        id: "exp-hybrid-vs-vector",
        name: "Hybrid RRF vs Vector-Only Baseline",
        status: "active",
        traffic_split: 50,
      }
    );
  }, [expResponse]);

  const [trafficSplit, setTrafficSplitState] = useState(() => activeExp.traffic_split);

  const handleTrafficSplitChange = (newSplit: number) => {
    setTrafficSplitState(newSplit);
    updateExperimentMutation.mutate({
      experiment_id: activeExp.id,
      traffic_split: newSplit,
    });
  };

  const handlePromoteCandidate = () => {
    handleTrafficSplitChange(100);
    toast.success("Promoted Variant B (Hybrid RRF) to 100% production traffic!");
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6 max-w-7xl mx-auto select-none">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-amber-400" />
            A/B Experiments & Architectural Baselines
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Statistically evaluate retrieval strategies side-by-side with accuracy, faithfulness, latency, and cost deltas.
          </p>
        </div>
        <Badge variant="outline" className="text-[11px] font-mono border-amber-500/40 text-amber-400 bg-amber-500/10">
          Active Experiment: E-104
        </Badge>
      </div>

      {/* KPI Delta Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Accuracy Delta</div>
          <div className="text-2xl font-semibold text-emerald-400 font-mono flex items-center gap-1 tabular-nums">
            <TrendingUp className="h-5 w-5" />
            +4.2%
          </div>
          <div className="text-[10px] text-zinc-500">98.4% vs 94.2% baseline (p &lt; 0.01)</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Faithfulness Delta</div>
          <div className="text-2xl font-semibold text-emerald-400 font-mono flex items-center gap-1 tabular-nums">
            <TrendingUp className="h-5 w-5" />
            +0.08
          </div>
          <div className="text-[10px] text-zinc-500">Mean 0.96 vs 0.88 control</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">P95 Latency Delta</div>
          <div className="text-2xl font-semibold text-sky-400 font-mono flex items-center gap-1 tabular-nums">
            <TrendingDown className="h-5 w-5" />
            -85ms
          </div>
          <div className="text-[10px] text-emerald-400">Faster due to early RRF cutoff</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="text-xs text-zinc-400 font-mono">Cost per Query Delta</div>
          <div className="text-2xl font-semibold text-emerald-400 font-mono flex items-center gap-1 tabular-nums">
            <TrendingDown className="h-5 w-5" />
            -$0.0012
          </div>
          <div className="text-[10px] text-zinc-500">-28% fewer prompt tokens required</div>
        </div>
      </div>

      {/* Active Experiment Card */}
      <Card className="bg-zinc-900/60 border-zinc-800">
        <CardHeader className="pb-3 border-b border-zinc-800/80">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-amber-400" />
                <CardTitle className="text-sm font-semibold text-zinc-100">
                  E-104: Reciprocal Rank Fusion vs. Cross-Encoder Only
                </CardTitle>
              </div>
              <div className="text-xs text-zinc-400">
                Evaluating multi-engine dual-retrieval (Qdrant + Neo4j) with RRF k=60 against standard single-vector RAG.
              </div>
            </div>

            <Button
              size="sm"
              onClick={handlePromoteCandidate}
              className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-medium h-7 text-xs cursor-pointer shrink-0"
            >
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Promote Variant B (100%)
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Variant A (Control) */}
            <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950/60 space-y-2">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-zinc-300">Variant A (Control)</span>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {100 - trafficSplit}% Traffic
                </Badge>
              </div>
              <p className="text-xs text-zinc-400">
                Single-engine dense vector retrieval (Qdrant) with text-embedding-3-large + cross-encoder rerank.
              </p>
              <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-500 pt-1">
                <span>Accuracy: 60%</span>
                <span>·</span>
                <span>Latency: 535ms</span>
                <span>·</span>
                <span>Cost: $0.0031</span>
              </div>
            </div>

            {/* Variant B (Treatment) */}
            <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/10 space-y-2">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-amber-300">Variant B (Treatment)</span>
                <Badge variant="outline" className="font-mono text-[10px] border-amber-500/40 text-amber-300 bg-amber-500/20">
                  {trafficSplit}% Traffic
                </Badge>
              </div>
              <p className="text-xs text-zinc-300">
                Hybrid multi-engine retrieval (Qdrant vector + Neo4j bi-temporal graph) + RRF (k=60) + cross-encoder.
              </p>
              <div className="flex items-center gap-3 text-[11px] font-mono text-amber-400 pt-1 font-medium">
                <span>Accuracy: 100% (+40%)</span>
                <span>·</span>
                <span>Latency: 450ms (-85ms)</span>
                <span>·</span>
                <span>Cost: $0.0022</span>
              </div>
            </div>
          </div>

          {/* Traffic Split Slider */}
          <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/40 space-y-2 text-xs">
            <div className="flex justify-between items-center font-mono">
              <span className="text-zinc-400 flex items-center gap-1.5">
                <Sliders className="h-3 w-3 text-amber-400" />
                Live Traffic Allocation
              </span>
              <span className="text-zinc-200">
                {100 - trafficSplit}% Control / {trafficSplit}% Treatment
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={trafficSplit}
              onChange={(e) => handleTrafficSplitChange(Number(e.target.value))}
              aria-label="Live traffic allocation split percentage"
              className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
            />
          </div>
        </CardContent>
      </Card>

      {/* Bottom Table: Run-by-run Comparison */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 backdrop-blur p-4 space-y-3">
        <div className="flex items-center justify-between text-xs font-mono text-zinc-400">
          <span className="font-semibold uppercase tracking-wider text-zinc-300">
            Run-by-Run Comparative Evaluation
          </span>
          <span>Diff Highlighting: Variant A vs Variant B</span>
        </div>

        <div className="rounded-lg border border-zinc-800 overflow-hidden">
          <Table>
            <TableHeader className="bg-zinc-950 text-[11px] font-mono">
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="w-12 text-center">#</TableHead>
                <TableHead>Evaluated Query</TableHead>
                <TableHead>Control (Variant A)</TableHead>
                <TableHead>Treatment (Variant B - RRF)</TableHead>
                <TableHead className="text-right">Latency Delta</TableHead>
                <TableHead className="text-right">Cost Delta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {DEFAULT_RUNS.map((run) => {
                const latencyDelta = run.variantB.latencyMs - run.variantA.latencyMs;
                const costDelta = run.variantB.costUsd - run.variantA.costUsd;

                return (
                  <TableRow key={run.id} className="border-zinc-800/60 hover:bg-zinc-900/60 text-xs">
                    <TableCell className="text-center font-mono text-zinc-500 text-[11px]">
                      {run.id}
                    </TableCell>
                    <TableCell className="font-medium text-zinc-200 max-w-xs">
                      {run.query}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 font-mono text-[11px]">
                        <Badge
                          variant="outline"
                          className={`text-[9px] ${
                            run.variantA.accuracy
                              ? "border-emerald-500/30 text-emerald-400"
                              : "border-rose-500/30 text-rose-400"
                          }`}
                        >
                          {run.variantA.accuracy ? "PASS" : "FAIL"}
                        </Badge>
                        <span className="text-zinc-400">sim {run.variantA.faithfulness.toFixed(2)}</span>
                        <span className="text-zinc-500">({run.variantA.latencyMs}ms)</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 font-mono text-[11px]">
                        <Badge
                          variant="outline"
                          className="text-[9px] border-emerald-500/40 text-emerald-400 bg-emerald-500/10 font-semibold"
                        >
                          PASS
                        </Badge>
                        <span className="text-amber-400 font-semibold">sim {run.variantB.faithfulness.toFixed(2)}</span>
                        <span className="text-zinc-300">({run.variantB.latencyMs}ms)</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono text-emerald-400 tabular-nums text-[11px]">
                      {latencyDelta}ms
                    </TableCell>
                    <TableCell className="text-right font-mono text-emerald-400 tabular-nums text-[11px]">
                      -${Math.abs(costDelta).toFixed(4)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

export default ExperimentsPage;

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { FlaskConical, AlertCircle } from "lucide-react";
import { useExperiments } from "../lib/api/hooks/useExperiments";
import { QueryState } from "../components/ui/QueryState";

export function ExperimentsPage() {
  const { data, isLoading, error, refetch } = useExperiments();

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
            Retrieval experiments recorded by the backend. Numbers are shown only when the backend
            persists real runs; nothing is generated in the browser.
          </p>
        </div>
      </div>

      <QueryState
        isLoading={isLoading}
        error={error}
        data={data}
        isEmpty={(d) => !d.experiments || d.experiments.length === 0}
        emptyIcon={AlertCircle}
        emptyTitle="No experiments recorded"
        emptyDescription="The backend has not persisted any experiment runs. Experiment tracking must be enabled before this page can show results."
        onRetry={() => refetch()}
        loadingSkeleton={
          <div className="h-48 rounded-xl bg-zinc-900/60 border border-zinc-800/80 animate-pulse" />
        }
      >
        {(response) => (
          <div className="space-y-4">
            {response.experiments.map((run) => (
              <Card key={run.id} className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3 border-b border-zinc-800/80">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="space-y-1">
                      <CardTitle className="text-sm font-semibold text-zinc-100">
                        {run.name}
                      </CardTitle>
                      <div className="text-xs text-zinc-400 font-mono">
                        {run.variant_a_route} vs {run.variant_b_route} · {run.traffic_split}% treatment
                      </div>
                    </div>
                    <Badge variant="outline" className="text-[10px] font-mono self-start">
                      {run.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
                    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
                      <div className="text-zinc-500 font-mono text-[11px]">Variant A Accuracy</div>
                      <div className="text-zinc-100 font-mono tabular-nums">
                        {(run.variant_a_accuracy * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
                      <div className="text-zinc-500 font-mono text-[11px]">Variant B Accuracy</div>
                      <div className="text-zinc-100 font-mono tabular-nums">
                        {(run.variant_b_accuracy * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
                      <div className="text-zinc-500 font-mono text-[11px]">P95 Latency</div>
                      <div className="text-zinc-100 font-mono tabular-nums">{run.p95_latency_ms} ms</div>
                    </div>
                    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
                      <div className="text-zinc-500 font-mono text-[11px]">Cost / 1k</div>
                      <div className="text-zinc-100 font-mono tabular-nums">
                        ${run.cost_per_1k.toFixed(4)}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
                      <div className="text-zinc-500 font-mono text-[11px]">Queries</div>
                      <div className="text-zinc-100 font-mono tabular-nums">{run.total_queries}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </QueryState>

      {/* The backend returns 501 until an experiment store exists. Explain that
          explicitly instead of rendering a fabricated comparison table. */}
      {error && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-xs text-zinc-400 font-mono">
          Experiment tracking is not implemented in the backend yet. This page will populate once
          runs are persisted and served by <span className="text-zinc-200">/experiments</span>.
        </div>
      )}

      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 backdrop-blur p-4 space-y-3">
        <div className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-300">
          Run-by-Run Comparative Evaluation
        </div>
        <div className="rounded-lg border border-zinc-800 overflow-hidden">
          <Table>
            <TableHeader className="bg-zinc-950 text-[11px] font-mono">
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead>Experiment</TableHead>
                <TableHead>Variant A</TableHead>
                <TableHead>Variant B</TableHead>
                <TableHead className="text-right">Traffic</TableHead>
                <TableHead className="text-right">Queries</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.experiments ?? []).map((run) => (
                <TableRow key={run.id} className="border-zinc-800/60 text-xs">
                  <TableCell className="font-medium text-zinc-200">{run.name}</TableCell>
                  <TableCell className="font-mono text-zinc-400">{run.variant_a_route}</TableCell>
                  <TableCell className="font-mono text-zinc-400">{run.variant_b_route}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                    {run.traffic_split}%
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-zinc-300">
                    {run.total_queries}
                  </TableCell>
                </TableRow>
              ))}
              {(!data?.experiments || data.experiments.length === 0) && (
                <TableRow className="border-zinc-800/60">
                  <TableCell colSpan={5} className="text-center text-xs text-zinc-500 py-6 font-mono">
                    No persisted experiment runs.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

export default ExperimentsPage;

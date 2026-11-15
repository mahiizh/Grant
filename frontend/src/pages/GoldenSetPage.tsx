import { useMemo, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Play, RotateCw, Search, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useGoldenDataset, useRunGoldenEval } from "../lib/api/hooks/useEvals";
import { QueryState } from "../components/ui/QueryState";
import type { components } from "../lib/api/schema";

type GoldenEvalReport = components["schemas"]["GoldenEvalRunResponse"];

export function GoldenSetPage() {
  const { data: datasetResponse, isLoading, error, refetch } = useGoldenDataset();
  const runGoldenEvalMutation = useRunGoldenEval();

  const [evalReport, setEvalReport] = useState<GoldenEvalReport | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  const pairs = useMemo(() => datasetResponse?.questions ?? [], [datasetResponse]);

  const handleRunEvalGate = () => {
    toast.info("Executing golden-set evaluation gate...");
    runGoldenEvalMutation.mutate(
      {},
      {
        onSuccess: (data) => {
          setEvalReport(data);
          toast.success(
            `Evaluation ${data.status}: ${(data.accuracy * 100).toFixed(1)}% on ${data.total_questions} questions.`
          );
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Evaluation run failed");
        },
      }
    );
  };

  const filteredPairs = pairs.filter(
    (p) =>
      p.question.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.expected_answer.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.expected_route.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6 max-w-7xl mx-auto select-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            Golden Set Benchmark & Eval Gate
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Regression gate evaluating the golden set against ground-truth pairs. Results appear only
            after a real backend run completes.
          </p>
        </div>

        <Button
          size="sm"
          onClick={handleRunEvalGate}
          disabled={runGoldenEvalMutation.isPending}
          className="bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-medium h-8 text-xs cursor-pointer disabled:opacity-40"
        >
          {runGoldenEvalMutation.isPending ? (
            <>
              <RotateCw className="h-3.5 w-3.5 mr-1.5 animate-spin" />
              Evaluating...
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Run Eval Gate
            </>
          )}
        </Button>
      </div>

      {/* Eval Gate Summary Report Card — populated only from the real response */}
      {evalReport && (
        <Card className="bg-zinc-900/60 border-emerald-500/30">
          <CardHeader className="pb-3 border-b border-zinc-800/60">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-zinc-100">
                Eval Gate Status: {evalReport.status}
              </CardTitle>
              <Badge variant="outline" className="text-[10px] font-mono">
                Split: {evalReport.split}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="text-zinc-400 font-mono text-[11px]">Accuracy</div>
              <div className="text-xl font-semibold text-emerald-400 font-mono tabular-nums">
                {(evalReport.accuracy * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-zinc-500">
                {evalReport.total_questions} questions evaluated
              </div>
            </div>

            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="text-zinc-400 font-mono text-[11px]">Cache Hit Rate</div>
              <div className="text-xl font-semibold text-amber-400 font-mono tabular-nums">
                {(evalReport.cache_hit_rate * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-zinc-500">Recorded during this run</div>
            </div>

            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="text-zinc-400 font-mono text-[11px]">Cost</div>
              <div className="text-xl font-semibold text-sky-400 font-mono tabular-nums">
                ${evalReport.total_cost_usd.toFixed(4)}
              </div>
              <div className="text-[10px] text-zinc-500">Budget ${evalReport.budget_usd.toFixed(2)}</div>
            </div>

            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-950/60 space-y-1">
              <div className="text-zinc-400 font-mono text-[11px]">Run</div>
              <div className="text-sm font-semibold text-zinc-200 font-mono truncate">
                {evalReport.run_id}
              </div>
              <div className="text-[10px] text-zinc-500">
                {evalReport.completed_at ? "Completed" : "In progress"}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Regression Suite Table */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 backdrop-blur p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
          <div className="relative w-64">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-2 text-zinc-500" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search benchmark questions..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-md pl-8 pr-3 py-1 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-700 font-sans"
            />
          </div>
          <span className="text-zinc-500">
            {filteredPairs.length} of {pairs.length} benchmark pairs
          </span>
        </div>

        <QueryState
          isLoading={isLoading}
          error={error}
          data={datasetResponse}
          isEmpty={(d) => !d.questions || d.questions.length === 0}
          emptyIcon={ShieldCheck}
          emptyTitle="No golden pairs found"
          emptyDescription="The backend golden dataset is empty. Add pairs before running the eval gate."
          onRetry={() => refetch()}
          loadingSkeleton={
            <div className="h-48 rounded-xl bg-zinc-900/60 border border-zinc-800/80 animate-pulse" />
          }
        >
          {() => (
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <Table>
                <TableHeader className="bg-zinc-950 text-[11px] font-mono">
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="w-12 text-center">#</TableHead>
                    <TableHead>Evaluation Query</TableHead>
                    <TableHead>Ground Truth Answer</TableHead>
                    <TableHead>Expected Route</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Split</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredPairs.map((pair, idx) => (
                    <TableRow key={pair.id} className="border-zinc-800/60 hover:bg-zinc-900/60 text-xs">
                      <TableCell className="text-center font-mono text-zinc-500 text-[11px]">
                        {idx + 1}
                      </TableCell>
                      <TableCell className="font-medium text-zinc-200 max-w-xs">
                        {pair.question}
                      </TableCell>
                      <TableCell className="text-zinc-400 text-[11px] max-w-sm line-clamp-2">
                        {pair.expected_answer}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] font-mono">
                          {pair.expected_route}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-[11px] text-zinc-400">
                        {pair.category}
                      </TableCell>
                      <TableCell className="text-right font-mono text-[11px] text-zinc-400">
                        {pair.split}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </QueryState>
      </div>
    </div>
  );
}

export default GoldenSetPage;

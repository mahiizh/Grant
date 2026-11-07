import { useState, useMemo } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Sparkles,
  Sliders,
  Database,
  Search,
  Network,
  RotateCcw,
} from "lucide-react";
import { useRetrievalCompare } from "../lib/api/hooks/useRetrieval";

interface RetrievalCandidate {
  id: string;
  title: string;
  snippet: string;
  vectorRank: number;
  vectorScore: number;
  bm25Rank: number;
  bm25Score: number;
  graphRank: number | null;
  tier: 1 | 2 | 3;
  crossEncoderScore?: number;
}

export function RetrievalPage() {
  const [rrfK, setRrfK] = useState(60);
  const [vectorThreshold, setVectorThreshold] = useState(0.8);
  const [crossEncoderCutoff, setCrossEncoderCutoff] = useState(0.85);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>("chunk-4");

  const { data: compareResponse } = useRetrievalCompare({
    query: "Transactional Outbox postgres failure",
    k: rrfK,
    vectorCutoff: vectorThreshold,
    crossEncoderCutoff,
  });

  const candidatesList: RetrievalCandidate[] = useMemo(() => {
    if (compareResponse?.candidates && compareResponse.candidates.length > 0) {
      return compareResponse.candidates.map((c) => ({
        id: c.chunk_id,
        title: c.doc_title,
        snippet: c.text,
        vectorRank: (c as any).vector_rank || 1,
        vectorScore: c.vector_score,
        bm25Rank: (c as any).bm25_rank || 1,
        bm25Score: c.bm25_score,
        graphRank: (c as any).graph_rank ?? 1,
        tier: ((c as any).tier || 1) as 1 | 2 | 3,
        crossEncoderScore: c.cross_encoder_score,
      }));
    }
    return [];
  }, [compareResponse]);

  // Calculate RRF score for each candidate based on dynamic k:
  // RRF(d) = sum( 1 / (k + rank) )
  const fusedResults = useMemo(() => {
    return candidatesList.map((c) => {
      let score = 0;
      if (c.vectorScore >= vectorThreshold) {
        score += 1 / (rrfK + c.vectorRank);
      }
      if (c.bm25Rank > 0) {
        score += 1 / (rrfK + c.bm25Rank);
      }
      if (c.graphRank !== null) {
        score += 1 / (rrfK + c.graphRank);
      }
      return { ...c, rrfScore: score };
    }).sort((a, b) => b.rrfScore - a.rrfScore);
  }, [candidatesList, rrfK, vectorThreshold]);

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6 max-w-7xl mx-auto select-none">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <Layers className="h-5 w-5 text-amber-400" />
            Retrieval & Reciprocal Rank Fusion (RRF) Inspector
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Compare dense vector embeddings, sparse BM25 keyword matching, and Neo4j graph traversal with live rank-shift telemetry.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-[11px] font-mono border-zinc-800 text-zinc-400">
            Formula: RRF = Σ 1/(k + rank)
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setRrfK(60);
              setVectorThreshold(0.8);
              setCrossEncoderCutoff(0.85);
            }}
            className="h-7 text-xs border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200"
          >
            <RotateCcw className="h-3 w-3 mr-1" />
            Reset
          </Button>
        </div>
      </div>

      {/* Sliders Tuning Controls Bar */}
      <div className="p-4 rounded-xl border border-zinc-800/80 bg-zinc-900/60 backdrop-blur grid grid-cols-1 md:grid-cols-3 gap-6 text-xs">
        {/* RRF k slider */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="font-mono text-zinc-300 font-semibold flex items-center gap-1.5">
              <Sliders className="h-3.5 w-3.5 text-amber-400" />
              RRF Constant (k): {rrfK}
            </span>
            <span className="text-[10px] font-mono text-zinc-500">default 60</span>
          </div>
          <input
            type="range"
            min={10}
            max={120}
            step={5}
            value={rrfK}
            onChange={(e) => setRrfK(Number(e.target.value))}
            aria-label="RRF constant k"
            className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
          />
          <div className="text-[10px] text-zinc-500 leading-relaxed">
            Lower k values give higher weight to top-ranked outliers across modalities.
          </div>
        </div>

        {/* Vector Similarity Threshold */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="font-mono text-zinc-300 font-semibold flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-sky-400" />
              Vector Cosine Cutoff: {vectorThreshold.toFixed(2)}
            </span>
            <span className="text-[10px] font-mono text-zinc-500">min sim</span>
          </div>
          <input
            type="range"
            min={0.6}
            max={0.95}
            step={0.02}
            value={vectorThreshold}
            onChange={(e) => setVectorThreshold(Number(e.target.value))}
            aria-label="Vector similarity threshold cutoff"
            className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-sky-400"
          />
          <div className="text-[10px] text-zinc-500 leading-relaxed">
            Filters out Qdrant semantic embeddings below the minimum cosine similarity floor.
          </div>
        </div>

        {/* Cross-Encoder Score Cutoff */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="font-mono text-zinc-300 font-semibold flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
              Cross-Encoder Cutoff: {crossEncoderCutoff.toFixed(2)}
            </span>
            <span className="text-[10px] font-mono text-zinc-500">rerank</span>
          </div>
          <input
            type="range"
            min={0.7}
            max={0.98}
            step={0.02}
            value={crossEncoderCutoff}
            onChange={(e) => setCrossEncoderCutoff(Number(e.target.value))}
            aria-label="Cross-encoder rerank score cutoff"
            className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-400"
          />
          <div className="text-[10px] text-zinc-500 leading-relaxed">
            Pre-generation gating: drops any candidate failing cross-encoder query-passage relevance.
          </div>
        </div>
      </div>

      {/* Side-by-Side Modality Columns */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* Column 1: Dense Vector (Qdrant) */}
        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800 text-xs">
            <span className="font-semibold text-sky-400 flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5" />
              1. Qdrant Dense
            </span>
            <span className="text-[10px] font-mono text-zinc-500">text-embed-3-large</span>
          </div>
          <div className="space-y-2">
            {[...candidatesList]
              .sort((a, b) => a.vectorRank - b.vectorRank)
              .map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelectedCandidateId(c.id)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                    selectedCandidateId === c.id
                      ? "border-sky-400/50 bg-sky-500/10"
                      : "border-zinc-800 bg-zinc-950/60 hover:bg-zinc-800/50"
                  }`}
                >
                  <div className="flex justify-between items-center text-[11px] font-mono mb-1">
                    <span className="text-zinc-300 font-semibold">Rank #{c.vectorRank}</span>
                    <span className="text-sky-400">{c.vectorScore.toFixed(3)}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 line-clamp-2">
                    {c.snippet}
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Column 2: Sparse BM25 */}
        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800 text-xs">
            <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
              <Search className="h-3.5 w-3.5" />
              2. BM25 Sparse
            </span>
            <span className="text-[10px] font-mono text-zinc-500">Term Exact</span>
          </div>
          <div className="space-y-2">
            {[...candidatesList]
              .sort((a, b) => a.bm25Rank - b.bm25Rank)
              .map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelectedCandidateId(c.id)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                    selectedCandidateId === c.id
                      ? "border-emerald-400/50 bg-emerald-500/10"
                      : "border-zinc-800 bg-zinc-950/60 hover:bg-zinc-800/50"
                  }`}
                >
                  <div className="flex justify-between items-center text-[11px] font-mono mb-1">
                    <span className="text-zinc-300 font-semibold">Rank #{c.bm25Rank}</span>
                    <span className="text-emerald-400">score {c.bm25Score}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 line-clamp-2">
                    {c.snippet}
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Column 3: Graph Traversal */}
        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800 text-xs">
            <span className="font-semibold text-violet-400 flex items-center gap-1.5">
              <Network className="h-3.5 w-3.5" />
              3. Neo4j Graph
            </span>
            <span className="text-[10px] font-mono text-zinc-500">2-Hop BFS</span>
          </div>
          <div className="space-y-2">
            {[...candidatesList]
              .filter((c) => c.graphRank !== null)
              .sort((a, b) => (a.graphRank || 99) - (b.graphRank || 99))
              .map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelectedCandidateId(c.id)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                    selectedCandidateId === c.id
                      ? "border-violet-400/50 bg-violet-500/10"
                      : "border-zinc-800 bg-zinc-950/60 hover:bg-zinc-800/50"
                  }`}
                >
                  <div className="flex justify-between items-center text-[11px] font-mono mb-1">
                    <span className="text-zinc-300 font-semibold">Hop #{c.graphRank}</span>
                    <span className="text-violet-400">Path connected</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 line-clamp-2">
                    {c.snippet}
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Column 4: Fused RRF Output */}
        <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-amber-500/20 text-xs">
            <span className="font-semibold text-amber-400 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" />
              4. Fused (RRF)
            </span>
            <span className="text-[10px] font-mono text-amber-500">Final Amalgam</span>
          </div>
          <div className="space-y-2">
            {fusedResults.map((c, idx) => {
              const finalRank = idx + 1;
              const shift = c.vectorRank - finalRank;

              return (
                <div
                  key={c.id}
                  onClick={() => setSelectedCandidateId(c.id)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-colors ${
                    selectedCandidateId === c.id
                      ? "border-amber-400 bg-amber-500/15 shadow-[0_0_8px_rgba(245,158,11,0.3)]"
                      : "border-zinc-800 bg-zinc-950/80 hover:bg-zinc-900"
                  }`}
                >
                  <div className="flex justify-between items-center text-[11px] font-mono mb-1">
                    <span className="text-amber-300 font-semibold">Final #{finalRank}</span>
                    <span className="text-zinc-400">{c.rrfScore.toFixed(4)}</span>
                  </div>
                  <div className="text-[11px] text-zinc-300 line-clamp-2">
                    {c.snippet}
                  </div>

                  {/* Rank Shift Indicator */}
                  <div className="mt-2 pt-1.5 border-t border-zinc-800/60 flex items-center justify-between text-[10px] font-mono">
                    <span className="text-zinc-500">from Vector #{c.vectorRank}</span>
                    {shift > 0 ? (
                      <span className="text-emerald-400 flex items-center gap-0.5">
                        <ArrowUpRight className="h-3 w-3" />
                        +{shift} spots
                      </span>
                    ) : shift < 0 ? (
                      <span className="text-rose-400 flex items-center gap-0.5">
                        <ArrowDownRight className="h-3 w-3" />
                        {shift} spots
                      </span>
                    ) : (
                      <span className="text-zinc-500 flex items-center gap-0.5">
                        <Minus className="h-3 w-3" />
                        no change
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default RetrievalPage;

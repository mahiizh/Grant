import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { EvidenceItem } from "../lib/api";
import { FileText, Layers, Hash } from "lucide-react";

export function RetrievalInspector({ evidence }: { evidence: EvidenceItem[] }) {
  if (!evidence || evidence.length === 0) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Layers className="h-4 w-4 text-blue-400" />
            Evidence & RRF Retrieval Inspector
          </CardTitle>
          <CardDescription>
            Passages retrieved by dense semantic search, sparse BM25 keyword matching, or Graph BFS traversal.
          </CardDescription>
        </CardHeader>
        <CardContent className="py-12 flex flex-col items-center justify-center text-zinc-500 text-sm">
          <FileText className="h-8 w-8 mb-2 opacity-30 animate-pulse" />
          No passages retrieved for this query.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-zinc-800 bg-zinc-900/60 flex flex-col h-full">
      <CardHeader className="pb-3 border-b border-zinc-800/60">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Layers className="h-4 w-4 text-blue-400" />
            Evidence & RRF Retrieval Inspector
          </CardTitle>
          <Badge variant="outline" className="font-mono text-[11px]">
            {evidence.length} Passages Ranked
          </Badge>
        </div>
        <CardDescription>
          RRF fused ranks (k=60), dense vector embeddings, and graph path evidence citations.
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4 flex-1 space-y-3 overflow-y-auto max-h-[500px]">
        {evidence.map((item, idx) => {
          const methodVariant =
            item.retrieval_method === "graph"
              ? "graph"
              : item.retrieval_method === "hybrid"
              ? "hybrid"
              : "vector";

          return (
            <div
              key={item.chunk_id + idx}
              className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-950/50 hover:border-zinc-700 transition-all flex flex-col gap-2"
            >
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="flex items-center justify-center h-5 w-5 rounded bg-zinc-800 text-[10px] font-bold text-zinc-300 font-mono">
                    #{idx + 1}
                  </span>
                  <Badge variant={methodVariant} className="text-[10px] py-0 px-2 font-mono uppercase">
                    {item.retrieval_method}
                  </Badge>
                  <span className="font-mono text-xs text-zinc-300 font-medium">{item.doc_id}</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-mono">
                  <Hash className="h-3 w-3 text-zinc-500" />
                  <span>Score: {item.score.toFixed(4)}</span>
                </div>
              </div>

              {/* Text Snippet */}
              <div className="p-2.5 rounded-lg bg-zinc-900/80 border border-zinc-800/40 text-xs text-zinc-300 font-mono leading-relaxed whitespace-pre-wrap">
                {item.text}
              </div>

              {/* Chunk Identifier and Path */}
              <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-1">
                <span className="font-mono text-zinc-400">Chunk: {item.chunk_id}</span>
                {item.path && item.path.length > 0 && (
                  <span className="text-purple-400 font-mono">Path Length: {item.path.length} hops</span>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

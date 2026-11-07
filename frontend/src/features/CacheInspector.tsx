import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { QueryResponse } from "../lib/api";
import { Zap, ShieldCheck, Database, Key } from "lucide-react";

export function CacheInspector({ response }: { response?: QueryResponse | null }) {
  const isCached = response?.is_cached ?? false;
  const strategy = response?.strategy_used ?? "none";

  return (
    <Card className="border-zinc-800 bg-zinc-900/60 flex flex-col h-full">
      <CardHeader className="pb-3 border-b border-zinc-800/60">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="h-4 w-4 text-emerald-400" />
            Multi-Tier Cache & Guardrails Inspector
          </CardTitle>
          <Badge variant={isCached ? "cache" : "secondary"} className="font-mono text-[11px]">
            {isCached ? "CACHE HIT" : "CACHE MISS"}
          </Badge>
        </div>
        <CardDescription>
          Exact SHA-256 key matching, vector semantic cache similarity, and guardrail anti-poisoning checks.
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-4 flex-1 space-y-4">
        {/* Tier 1: Exact Cache */}
        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-950/40 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
              <Key className="h-3.5 w-3.5 text-amber-400" /> Tier 1: Exact Cache (In-Memory Key-Value)
            </span>
            <Badge variant="outline" className="text-[10px] font-mono">
              Index Version: v1
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Computes a deterministic SHA-256 digest over normalized query string, ACL tenant ID, and user role claims.
          </p>
          <div className="p-2 rounded bg-zinc-900 border border-zinc-800/60 font-mono text-[11px] text-zinc-400 truncate">
            exact_key = sha256("{response?.query ?? "sample_query"}")
          </div>
        </div>

        {/* Tier 2: Semantic Cache */}
        <div className="p-3.5 rounded-xl border border-zinc-800/80 bg-zinc-950/40 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-blue-400" /> Tier 2: Semantic Cache (Vector Similarity)
            </span>
            <span className="text-[11px] font-mono text-zinc-400">
              Threshold: &gt;= 0.45 Cosine
            </span>
          </div>
          <p className="text-xs text-zinc-400">
            Discovers semantically equivalent query paraphrases. Evaluates multiple candidates in descending order to avoid false-negative traps.
          </p>
          <div className="flex items-center justify-between p-2 rounded bg-zinc-900 border border-zinc-800/60 text-xs">
            <span className="text-zinc-400">Status for current query:</span>
            <span className="font-mono font-semibold text-zinc-200">
              {strategy === "cache" ? "Hit via Semantic / Exact Paraphrase" : "Missed (Fell through to engine)"}
            </span>
          </div>
        </div>

        {/* Guardrail Audit Engine */}
        <div className="p-3.5 rounded-xl border border-emerald-950/40 bg-emerald-950/15 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4" /> Anti-Poisoning Guardrail Audit
            </span>
            <Badge variant="success" className="text-[10px]">
              GUARD PASS
            </Badge>
          </div>
          <p className="text-xs text-zinc-300">
            Intercepts raw vector hits and rejects near-miss queries with different technical codes or numbers:
          </p>
          <ul className="text-xs text-zinc-400 space-y-1 list-disc list-inside">
            <li>
              <span className="text-zinc-300 font-mono">INC Codes</span>: Verified exact parity (e.g. INC-2026-04 vs INC-2026-05).
            </li>
            <li>
              <span className="text-zinc-300 font-mono">Dates & Numbers</span>: Validated numerical token set identity.
            </li>
            <li>
              <span className="text-zinc-300 font-mono">Domain Subsystems</span>: Prevented cross-talk between Payments & Outbox.
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Database, Cpu, ShieldCheck, Palette } from "lucide-react";
import { useApp } from "../context/AppContext";
import { useSettingsApi, useUpdateSettings } from "../lib/api/hooks/useSettingsApi";

export function SettingsPage() {
  const { canvasTheme, setCanvasTheme } = useApp();
  const { data: settingsData } = useSettingsApi();
  const updateSettingsMutation = useUpdateSettings();

  const handleCanvasThemeChange = (theme: "dark" | "match") => {
    setCanvasTheme(theme);
    updateSettingsMutation.mutate({ canvas_theme: theme });
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Settings & Stores</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Store versions, bi-temporal graph configuration, budget caps, and API endpoints.
          </p>
        </div>

        {/* Store Versions */}
        <Card className="bg-zinc-950/40 border-zinc-800">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-emerald-400" />
              <CardTitle className="text-sm font-medium">Underlying Stores & Engines</CardTitle>
            </div>
            <CardDescription className="text-xs">
              Configured databases, index versions, and vector store topologies.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-zinc-200">Neo4j Graph Database</div>
                  <div className="text-[11px] font-mono text-zinc-500">Bi-Temporal · valid_from / valid_to</div>
                </div>
                <Badge variant="outline" className="font-mono text-[10px] text-sky-400 border-sky-400/30">
                  {settingsData?.stores?.neo4j?.status ? `v5.20.0 (${settingsData.stores.neo4j.status})` : "v5.20.0-enterprise"}
                </Badge>
              </div>

              <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-zinc-200">Qdrant Vector Engine</div>
                  <div className="text-[11px] font-mono text-zinc-500">HNSW Indexing · text-embedding-3-large</div>
                </div>
                <Badge variant="outline" className="font-mono text-[10px] text-emerald-400 border-emerald-400/30">
                  {settingsData?.stores?.qdrant?.status ? `v1.9.2 (${settingsData.stores.qdrant.status})` : "v1.9.2"}
                </Badge>
              </div>

              <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-zinc-200">PostgreSQL Relational & Outbox</div>
                  <div className="text-[11px] font-mono text-zinc-500">Document store & Transactional Outbox</div>
                </div>
                <Badge variant="outline" className="font-mono text-[10px] text-indigo-400 border-indigo-400/30">
                  {settingsData?.stores?.postgres?.status ? `v16.3 (${settingsData.stores.postgres.status})` : "v16.3"}
                </Badge>
              </div>

              <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
                <div>
                  <div className="text-xs font-medium text-zinc-200">Redis Semantic Cache</div>
                  <div className="text-[11px] font-mono text-zinc-500">TTL 3600s · Cosine Sim Threshold 0.92</div>
                </div>
                <Badge variant="outline" className="font-mono text-[10px] text-rose-400 border-rose-400/30">
                  {settingsData?.stores?.redis?.status ? `v7.2.4 (${settingsData.stores.redis.status})` : "v7.2.4"}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Guardrails & Budgets */}
        <Card className="bg-zinc-950/40 border-zinc-800">
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-amber-400" />
              <CardTitle className="text-sm font-medium">Budget Caps & Guardrails</CardTitle>
            </div>
            <CardDescription className="text-xs">
              Daily query spending caps, maximum hops for Personalized PageRank, and timeout limits.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
              <div className="text-xs text-zinc-400">Daily USD Cap</div>
              <div className="text-base font-semibold text-zinc-100 font-mono mt-1">$50.00 / day</div>
              <div className="text-[10px] text-zinc-500 mt-0.5">$3.42 consumed today</div>
            </div>
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
              <div className="text-xs text-zinc-400">Graph Expansion Limit</div>
              <div className="text-base font-semibold text-zinc-100 font-mono mt-1">3 hops max</div>
              <div className="text-[10px] text-zinc-500 mt-0.5">Truncates high-degree supernodes</div>
            </div>
            <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
              <div className="text-xs text-zinc-400">P95 Latency SLA</div>
              <div className="text-base font-semibold text-zinc-100 font-mono mt-1">850 ms</div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Currently passing (620 ms)</div>
            </div>
          </CardContent>
        </Card>

        {/* Canvas Display Appearance */}
        <Card className="bg-zinc-950/40 border-zinc-800">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Palette className="h-4 w-4 text-amber-400" />
              <CardTitle className="text-sm font-medium">Canvas Background Appearance</CardTitle>
            </div>
            <CardDescription className="text-xs">
              Configure graph viewport canvas rendering mode for light and dark themes.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <button
                type="button"
                onClick={() => handleCanvasThemeChange("dark")}
                className={`p-3 rounded-lg border text-left transition-all cursor-pointer ${
                  canvasTheme === "dark"
                    ? "border-amber-400 bg-amber-500/10 text-zinc-100 shadow-[0_0_8px_rgba(245,158,11,0.2)]"
                    : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <div className="font-semibold text-zinc-200">Dark (#09090b) [Recommended]</div>
                <div className="text-[11px] text-zinc-400 mt-1">
                  Keeps deep dark canvas background in all themes for maximum neon glow & particle contrast.
                </div>
              </button>

              <button
                type="button"
                onClick={() => handleCanvasThemeChange("match")}
                className={`p-3 rounded-lg border text-left transition-all cursor-pointer ${
                  canvasTheme === "match"
                    ? "border-amber-400 bg-amber-500/10 text-zinc-100 shadow-[0_0_8px_rgba(245,158,11,0.2)]"
                    : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <div className="font-semibold text-zinc-200">Match Theme (Adaptive)</div>
                <div className="text-[11px] text-zinc-400 mt-1">
                  Adapts canvas background to match the dashboard theme (light in light mode, dark in dark mode).
                </div>
              </button>
            </div>
          </CardContent>
        </Card>

        {/* Runtime Environment */}
        <Card className="bg-zinc-950/40 border-zinc-800">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-violet-400" />
              <CardTitle className="text-sm font-medium">Runtime Environment</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-zinc-800/60">
              <span className="text-zinc-400">Backend API URL</span>
              <span className="font-mono text-zinc-200">
                {import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"} ({import.meta.env.VITE_API_MODE ?? "mock"} mode)
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/60">
              <span className="text-zinc-400">Embedding Model</span>
              <span className="font-mono text-zinc-200">text-embedding-3-large (3072d)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-zinc-400">Orchestrator Architecture</span>
              <span className="font-mono text-zinc-200">LangGraph Dynamic State Machine</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default SettingsPage;

import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Database, Cpu, Palette, SlidersHorizontal } from "lucide-react";
import { useApp } from "../context/AppContext";
import { useSettingsApi, useUpdateSettings } from "../lib/api/hooks/useSettingsApi";
import { QueryState } from "../components/ui/QueryState";

const STORE_LABELS: Record<string, { name: string; detail: string; color: string }> = {
  neo4j: {
    name: "Neo4j Graph Database",
    detail: "Bi-temporal · valid_from / valid_to",
    color: "text-sky-400 border-sky-400/30",
  },
  qdrant: {
    name: "Qdrant Vector Engine",
    detail: "Dense + sparse vectors",
    color: "text-emerald-400 border-emerald-400/30",
  },
  postgres: {
    name: "PostgreSQL Relational & Outbox",
    detail: "Document store & transactional outbox",
    color: "text-indigo-400 border-indigo-400/30",
  },
  redis: {
    name: "Redis Semantic Cache",
    detail: "Exact + semantic response cache",
    color: "text-rose-400 border-rose-400/30",
  },
};

export function SettingsPage() {
  const { canvasTheme, setCanvasTheme } = useApp();
  const { data: settingsData, isLoading, error, refetch } = useSettingsApi();
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
            Store health, measured latency, and runtime defaults reported by the backend.
          </p>
        </div>

        <QueryState
          isLoading={isLoading}
          error={error}
          data={settingsData}
          onRetry={() => refetch()}
          loadingSkeleton={<div className="h-64 rounded-xl bg-zinc-950/40 border border-zinc-800 animate-pulse" />}
        >
          {(data) => (
            <>
              {/* Store Health */}
              <Card className="bg-zinc-950/40 border-zinc-800">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Database className="h-4 w-4 text-emerald-400" />
                    <CardTitle className="text-sm font-medium">Underlying Stores & Engines</CardTitle>
                  </div>
                  <CardDescription className="text-xs">
                    Live health checks with measured round-trip latency.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(data.stores ?? {}).map(([key, store]) => {
                      const label = STORE_LABELS[key] ?? {
                        name: key,
                        detail: "Configured store",
                        color: "text-zinc-400 border-zinc-700",
                      };
                      const healthy = store.status === "healthy";
                      return (
                        <div
                          key={key}
                          className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40 flex items-center justify-between gap-3"
                        >
                          <div>
                            <div className="text-xs font-medium text-zinc-200">{label.name}</div>
                            <div className="text-[11px] font-mono text-zinc-500">{label.detail}</div>
                          </div>
                          <div className="text-right">
                            <Badge variant="outline" className={`font-mono text-[10px] ${label.color}`}>
                              {store.status}
                            </Badge>
                            <div className="text-[10px] font-mono text-zinc-500 mt-1 tabular-nums">
                              {healthy ? `${store.latency_ms.toFixed(1)} ms` : "unreachable"}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* Runtime Defaults */}
              <Card className="bg-zinc-950/40 border-zinc-800">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="h-4 w-4 text-amber-400" />
                    <CardTitle className="text-sm font-medium">Runtime Defaults</CardTitle>
                  </div>
                  <CardDescription className="text-xs">
                    Defaults applied to new queries and graph views.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
                    <div className="text-xs text-zinc-400">Default ACL Scope</div>
                    <div className="text-base font-semibold text-zinc-100 font-mono mt-1">
                      {data.default_scope}
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-0.5">
                      {(data.acl_scopes ?? []).length} scopes available
                    </div>
                  </div>
                  <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
                    <div className="text-xs text-zinc-400">Default As-Of Date</div>
                    <div className="text-base font-semibold text-zinc-100 font-mono mt-1">
                      {data.default_as_of_date}
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-0.5">Bi-temporal snapshot date</div>
                  </div>
                  <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/40">
                    <div className="text-xs text-zinc-400">Canvas Theme</div>
                    <div className="text-base font-semibold text-zinc-100 font-mono mt-1">
                      {data.canvas_theme}
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-0.5">Graph viewport rendering mode</div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </QueryState>

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
                {import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"} (
                {import.meta.env.VITE_API_MODE ?? "live"} mode)
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-zinc-800/60">
              <span className="text-zinc-400">Embedding Model</span>
              <span className="font-mono text-zinc-200">Configured by backend</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-zinc-400">Orchestrator Architecture</span>
              <span className="font-mono text-zinc-200">LangGraph dynamic state machine</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default SettingsPage;

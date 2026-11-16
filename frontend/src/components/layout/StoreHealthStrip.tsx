import { useApp } from "../../context/AppContext";
import { useStoreHealth } from "../../lib/api/hooks/useSettingsApi";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

export function StoreHealthStrip({ compact = false }: { compact?: boolean }) {
  const { storeHealth } = useApp();
  const { data: readyData } = useStoreHealth();

  const isConfigured = (key: string) => {
    if (!readyData?.configured_stores) return true;
    return Boolean((readyData.configured_stores as Record<string, boolean>)[key]);
  };

  const latencyLabel = (value: number | null) => (value === null ? "—" : `${value}ms`);
  const eventsLabel = (value: number | null) => (value === null ? "— events" : `${value} events`);

  const stores = [
    {
      key: "postgres",
      label: "Postgres 16",
      health: isConfigured("postgres") ? storeHealth.postgres.status : "down",
      latency: latencyLabel(storeHealth.postgres.latencyMs),
    },
    {
      key: "qdrant",
      label: "Qdrant Vector",
      health: isConfigured("qdrant") ? storeHealth.qdrant.status : "down",
      latency: latencyLabel(storeHealth.qdrant.latencyMs),
    },
    {
      key: "neo4j",
      label: "Neo4j Graph",
      health: isConfigured("neo4j") ? storeHealth.neo4j.status : "down",
      latency: latencyLabel(storeHealth.neo4j.latencyMs),
    },
    {
      key: "redis",
      label: "Redis Cache",
      health: isConfigured("redis") ? storeHealth.redis.status : "down",
      latency: latencyLabel(storeHealth.redis.latencyMs),
    },
    {
      key: "outbox",
      label: "Outbox Lag",
      health: storeHealth.outboxLag.status,
      latency: eventsLabel(storeHealth.outboxLag.events),
    },
  ];

  const getDotColor = (status: string) => {
    switch (status) {
      case "healthy":
        return "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]";
      case "degraded":
      case "lagging":
        return "bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.5)]";
      case "unknown":
        return "bg-zinc-500";
      default:
        return "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.5)]";
    }
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className={`flex items-center gap-2 select-none ${compact ? "justify-center" : "justify-between"}`}>
        {!compact && (
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
            Store Mesh
          </span>
        )}
        <div className="flex items-center gap-1.5">
          {stores.map((s) => (
            <Tooltip key={s.key}>
              <TooltipTrigger asChild>
                <div className="p-1 rounded hover:bg-zinc-800/80 cursor-pointer transition-colors">
                  <span className={`block h-1.5 w-1.5 rounded-full ${getDotColor(s.health)}`} />
                </div>
              </TooltipTrigger>
              <TooltipContent side="top">
                <div className="text-[11px] font-sans">
                  <span className="font-semibold text-zinc-200 block">{s.label}</span>
                  <span className="text-zinc-400 font-mono text-[10px]">{s.latency} • {s.health}</span>
                </div>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </div>
    </TooltipProvider>
  );
}

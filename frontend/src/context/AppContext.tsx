import React, { createContext, useContext, useState, useEffect } from "react";

export type StoreStatus = "healthy" | "degraded" | "down" | "unknown";
export type OutboxStatus = "healthy" | "lagging" | "unknown";

export interface StoreHealth {
  postgres: { status: StoreStatus; latencyMs: number | null };
  qdrant: { status: StoreStatus; latencyMs: number | null };
  neo4j: { status: StoreStatus; latencyMs: number | null };
  redis: { status: StoreStatus; latencyMs: number | null };
  outboxLag: { events: number | null; status: OutboxStatus };
}

interface AppContextType {
  theme: "dark" | "light";
  setTheme: (theme: "dark" | "light") => void;
  canvasTheme: "dark" | "match";
  setCanvasTheme: (val: "dark" | "match") => void;
  aclScope: string;
  setAclScope: (scope: string) => void;
  asOfDate: string;
  setAsOfDate: (date: string) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  commandOpen: boolean;
  setCommandOpen: (open: boolean) => void;
  storeHealth: StoreHealth;
}

const DEFAULT_STORE_HEALTH: StoreHealth = {
  postgres: { status: "unknown", latencyMs: null },
  qdrant: { status: "unknown", latencyMs: null },
  neo4j: { status: "unknown", latencyMs: null },
  redis: { status: "unknown", latencyMs: null },
  outboxLag: { events: null, status: "unknown" },
};

function asStoreStatus(value: unknown): StoreStatus {
  return value === "healthy" || value === "degraded" || value === "down" ? value : "unknown";
}

function asOutboxStatus(value: unknown): OutboxStatus {
  return value === "healthy" || value === "lagging" ? value : "unknown";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<"dark" | "light">(() => {
    const saved = localStorage.getItem("grant_theme");
    return (saved as "dark" | "light") || "dark";
  });

  const [canvasTheme, setCanvasThemeState] = useState<"dark" | "match">(() => {
    const saved = localStorage.getItem("grant_canvas_theme");
    return (saved as "dark" | "match") || "dark";
  });

  const setCanvasTheme = (val: "dark" | "match") => {
    setCanvasThemeState(val);
    localStorage.setItem("grant_canvas_theme", val);
  };

  const [aclScope, setAclScope] = useState<string>("data-platform");
  const [asOfDate, setAsOfDate] = useState<string>("2026-04-12");
  const [commandOpen, setCommandOpen] = useState<boolean>(false);

  const [sidebarCollapsed, setSidebarCollapsedState] = useState<boolean>(() => {
    return localStorage.getItem("grant_sidebar_collapsed") === "true";
  });

  const [storeHealth, setStoreHealth] = useState<StoreHealth>(DEFAULT_STORE_HEALTH);

  const setTheme = (t: "dark" | "light") => {
    setThemeState(t);
    localStorage.setItem("grant_theme", t);
    if (t === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const setSidebarCollapsed = (collapsed: boolean) => {
    setSidebarCollapsedState(collapsed);
    localStorage.setItem("grant_sidebar_collapsed", String(collapsed));
  };

  // Sync theme with DOM initially
  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);

  // Health poll. Unknown is a real state: never invent a healthy store or a latency.
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("/api/v1/health");
        if (!res.ok) {
          setStoreHealth(DEFAULT_STORE_HEALTH);
          return;
        }
        const data = await res.json();
        const components = data.components ?? {};
        setStoreHealth({
          postgres: {
            status: asStoreStatus(components.postgres?.status),
            latencyMs: asNumber(components.postgres?.latency_ms),
          },
          qdrant: {
            status: asStoreStatus(components.qdrant?.status),
            latencyMs: asNumber(components.qdrant?.latency_ms),
          },
          neo4j: {
            status: asStoreStatus(components.neo4j?.status),
            latencyMs: asNumber(components.neo4j?.latency_ms),
          },
          redis: {
            status: asStoreStatus(components.redis?.status),
            latencyMs: asNumber(components.redis?.latency_ms),
          },
          outboxLag: {
            events: asNumber(data.outbox_lag),
            status: asOutboxStatus(components.outbox?.status),
          },
        });
      } catch {
        setStoreHealth(DEFAULT_STORE_HEALTH);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <AppContext.Provider
      value={{
        theme,
        setTheme,
        canvasTheme,
        setCanvasTheme,
        aclScope,
        setAclScope,
        asOfDate,
        setAsOfDate,
        sidebarCollapsed,
        setSidebarCollapsed,
        commandOpen,
        setCommandOpen,
        storeHealth,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
}

import React, { createContext, useContext, useState, useEffect } from "react";

export interface StoreHealth {
  postgres: { status: "healthy" | "degraded" | "down"; latencyMs: number };
  qdrant: { status: "healthy" | "degraded" | "down"; latencyMs: number };
  neo4j: { status: "healthy" | "degraded" | "down"; latencyMs: number };
  redis: { status: "healthy" | "degraded" | "down"; latencyMs: number };
  outboxLag: { events: number; status: "healthy" | "lagging" };
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
  postgres: { status: "healthy", latencyMs: 1.2 },
  qdrant: { status: "healthy", latencyMs: 2.4 },
  neo4j: { status: "healthy", latencyMs: 3.1 },
  redis: { status: "healthy", latencyMs: 0.8 },
  outboxLag: { events: 0, status: "healthy" },
};

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

  // Health poll with mock fallback
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("/api/v1/health");
        if (res.ok) {
          const data = await res.json();
          if (data.components) {
            setStoreHealth({
              postgres: {
                status: data.components.postgres?.status || "healthy",
                latencyMs: data.components.postgres?.latency_ms ?? 1.1,
              },
              qdrant: {
                status: data.components.qdrant?.status || "healthy",
                latencyMs: data.components.qdrant?.latency_ms ?? 2.2,
              },
              neo4j: {
                status: data.components.neo4j?.status || "healthy",
                latencyMs: data.components.neo4j?.latency_ms ?? 2.9,
              },
              redis: {
                status: data.components.redis?.status || "healthy",
                latencyMs: data.components.redis?.latency_ms ?? 0.7,
              },
              outboxLag: {
                events: data.outbox_lag ?? 0,
                status: data.components.outbox?.status || "healthy",
              },
            });
          }
        }
      } catch {
        // Fallback to default healthy state if backend not currently running
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

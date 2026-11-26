import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../../context/AppContext";

import { Button } from "../ui/button";
import { Search, Plus, Sun, Moon, ChevronRight } from "lucide-react";

export function Header() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { theme, setTheme, setCommandOpen } = useApp();

  // Compute clean breadcrumbs from route
  const getBreadcrumbs = () => {
    switch (pathname) {
      case "/":
      case "/ask":
        return { section: "Workspace", page: "Ask & Citations" };
      case "/overview":
        return { section: "Workspace", page: "Overview & KPIs" };
      case "/documents":
        return { section: "Workspace", page: "Documents & Ingestion" };
      case "/graph":
        return { section: "Workspace", page: "Knowledge Graph" };
      case "/settings":
        return { section: "System", page: "Settings & Stores" };
      default:
        return { section: "Workspace", page: "Overview" };
    }
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <header className="h-14 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-20 px-4 flex items-center justify-between select-none">
      {/* Left: Breadcrumbs */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-sans">
          <span className="text-zinc-500 font-normal">{breadcrumbs.section}</span>
          <ChevronRight className="h-3 w-3 text-zinc-600" />
          <span className="font-semibold text-zinc-200">{breadcrumbs.page}</span>
        </div>
      </div>

      {/* Right: Cmd+K, New Query, Theme Toggle */}
      <div className="flex items-center gap-2.5">
        {/* Global Cmd+K Search Trigger */}
        <button
          onClick={() => setCommandOpen(true)}
          className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-md border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-xs text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
          title="Search entities (Cmd+K)"
        >
          <Search className="h-3.5 w-3.5 text-zinc-500" />
          <span className="text-xs">Search...</span>
          <kbd className="h-4.5 px-1 rounded border border-zinc-700 bg-zinc-800 font-mono text-[9px] text-zinc-400 ml-1">
            ⌘K
          </kbd>
        </button>

        {/* New Query Primary Button */}
        <Button
          size="sm"
          onClick={() => navigate("/")}
          className="h-7 px-2.5 bg-zinc-100 text-zinc-950 hover:bg-zinc-200 text-xs gap-1 font-medium shadow-xs"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New query</span>
        </Button>

        {/* Theme Toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-1.5 rounded-md border border-zinc-800 hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? <Sun className="h-3.5 w-3.5 text-amber-400" /> : <Moon className="h-3.5 w-3.5 text-sky-400" />}
        </button>
      </div>
    </header>
  );
}

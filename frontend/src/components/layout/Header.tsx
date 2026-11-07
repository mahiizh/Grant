import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../../context/AppContext";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Search, Plus, Sun, Moon, Calendar, Shield, ChevronRight } from "lucide-react";

export function Header() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { theme, setTheme, aclScope, setAclScope, asOfDate, setAsOfDate, setCommandOpen } = useApp();

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
      case "/traces":
        return { section: "Inspect", page: "Traces & Spans" };
      case "/retrieval":
        return { section: "Inspect", page: "Retrieval & RRF" };
      case "/cache":
        return { section: "Inspect", page: "Cache & Guardrails" };
      case "/experiments":
        return { section: "Evaluate", page: "Experiments & Baselines" };
      case "/golden-set":
        return { section: "Evaluate", page: "Golden Benchmark Gate" };
      case "/settings":
        return { section: "System", page: "Settings & Stores" };
      default:
        return { section: "Workspace", page: "Overview" };
    }
  };

  const breadcrumbs = getBreadcrumbs();

  const isMockMode = (import.meta.env.VITE_API_MODE ?? "mock") === "mock";

  return (
    <header className="h-14 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-20 px-4 flex items-center justify-between select-none">
      {/* Left: Breadcrumbs & Sample Data Badge */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-sans">
          <span className="text-zinc-500 font-normal">{breadcrumbs.section}</span>
          <ChevronRight className="h-3 w-3 text-zinc-600" />
          <span className="font-semibold text-zinc-200">{breadcrumbs.page}</span>
        </div>

        {isMockMode && (
          <Badge variant="outline" className="text-[10px] font-mono py-0 px-1.5 border-amber-500/30 bg-amber-500/10 text-amber-400">
            Sample data
          </Badge>
        )}
      </div>

      {/* Right: ACL Switcher, As Of Date, Cmd+K, New Query, Theme Toggle */}
      <div className="flex items-center gap-2.5">
        {/* ACL Scope Switcher */}
        <div className="flex items-center gap-1.5">
          <Shield className="h-3.5 w-3.5 text-zinc-500 hidden sm:block" />
          <div className="w-40 sm:w-44">
            <Select value={aclScope} onValueChange={setAclScope}>
              <SelectTrigger className="h-7 text-[11px] font-mono">
                <SelectValue placeholder="Scope" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">scope: public</SelectItem>
                <SelectItem value="data-platform">scope: data-platform</SelectItem>
                <SelectItem value="core-banking">scope: core-banking</SelectItem>
                <SelectItem value="payments">scope: payments</SelectItem>
                <SelectItem value="sre-reliability">scope: sre-oncall</SelectItem>
                <SelectItem value="executive-audit">scope: executive-audit</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Bi-Temporal "As Of" Date Picker */}
        <div className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded-md border border-zinc-800 bg-zinc-950/60 text-xs">
          <Calendar className="h-3 w-3 text-zinc-500" />
          <span className="text-[10px] font-mono text-zinc-500">As of:</span>
          <input
            type="date"
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            className="bg-transparent border-0 text-[11px] font-mono text-zinc-300 focus:outline-none p-0 cursor-pointer"
          />
        </div>

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

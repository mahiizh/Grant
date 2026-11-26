import { useState } from "react";
import { ChevronDown, ChevronUp, Layers } from "lucide-react";

export interface LegendProps {
  colorBy: "type" | "tier";
}

export function GraphLegend({ colorBy }: LegendProps) {
  const [collapsed, setCollapsed] = useState(false);

  const typeItems = [
    { label: "Mechanisms [M]", color: "#F59E0B" }, // amber
    { label: "Databases [D]", color: "#38BDF8" }, // sky
    { label: "Teams & People [T/P]", color: "#8B5CF6" }, // violet
    { label: "Services [S]", color: "#10B981" }, // emerald
  ];

  const tierItems = [
    { label: "Tier 1: Authoritative (solid)", color: "#38BDF8", style: "border-b border-sky-400" },
    { label: "Tier 2: Derived docs (faint)", color: "#10B981", style: "border-b border-emerald-400" },
    { label: "Tier 3: Inferred (dashed)", color: "#F59E0B", style: "border-b border-dashed border-amber-400" },
  ];

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="absolute bottom-4 left-4 z-10 px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-950/80 backdrop-blur-md shadow-md text-xs text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors flex items-center gap-1.5 cursor-pointer"
        title="Expand Legend"
      >
        <Layers className="h-3.5 w-3.5 text-zinc-400" />
        <span className="text-[11px] font-mono">Legend</span>
        <ChevronUp className="h-3 w-3 text-zinc-500" />
      </button>
    );
  }

  return (
    <div className="absolute bottom-4 left-4 z-10 p-3 rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md shadow-xl text-xs text-zinc-300 pointer-events-auto max-w-xs transition-all select-none">
      <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Layers className="h-3 w-3 text-zinc-500" />
          Legend ({colorBy === "type" ? "Types" : "Tiers"})
        </span>
        <button
          onClick={() => setCollapsed(true)}
          className="text-zinc-500 hover:text-zinc-300 p-0.5 rounded cursor-pointer"
          title="Collapse Legend"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="space-y-1.5">
        {colorBy === "type" &&
          typeItems.map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0 shadow-sm"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-[11px] font-medium text-zinc-300">{item.label}</span>
            </div>
          ))}

        {colorBy === "tier" &&
          tierItems.map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-[11px] font-medium text-zinc-300">{item.label}</span>
            </div>
          ))}
      </div>

      <div className="mt-2.5 pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500 flex items-center justify-between font-mono">
        <span>Node = Degree</span>
        <span>Edges = Provenance</span>
      </div>
    </div>
  );
}

import { useState, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import type { GraphNode } from "../types/graph";
import { Search, ArrowUpDown } from "lucide-react";

export interface EntityTableProps {
  nodes: GraphNode[];
  onSelectNode: (nodeId: string) => void;
  selectedNodeId?: string | null;
}

type SortField = "name" | "type" | "degree";

export function EntityTable({ nodes, onSelectNode, selectedNodeId }: EntityTableProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [minDegree, setMinDegree] = useState<number>(0);
  const [sortField, setSortField] = useState<SortField>("degree");
  const [sortAsc, setSortAsc] = useState(false);

  const parentRef = useRef<HTMLDivElement>(null);

  const typeVariants: Record<string, "graph" | "vector" | "warning" | "success" | "secondary"> = {
    mechanism: "warning",
    database: "vector",
    person: "graph",
    team: "graph",
    service: "success",
  };

  const processedNodes = useMemo(() => {
    return nodes
      .filter((n) => {
        const matchesSearch =
          n.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          n.type.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesType = selectedType === "all" || n.type === selectedType;
        const matchesDegree = (n.degree ?? 0) >= minDegree;
        return matchesSearch && matchesType && matchesDegree;
      })
      .sort((a, b) => {
        let valA: string | number = sortField === "degree" ? (a.degree ?? 0) : a[sortField];
        let valB: string | number = sortField === "degree" ? (b.degree ?? 0) : b[sortField];
        if (typeof valA === "string") valA = valA.toLowerCase();
        if (typeof valB === "string") valB = valB.toLowerCase();

        if (valA < valB) return sortAsc ? -1 : 1;
        if (valA > valB) return sortAsc ? 1 : -1;
        return 0;
      });
  }, [nodes, searchTerm, selectedType, minDegree, sortField, sortAsc]);

  // Virtualizer for smooth rendering of large node lists
  const rowVirtualizer = useVirtualizer({
    count: processedNodes.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 38,
    overscan: 6,
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-zinc-950 p-3 space-y-2.5 overflow-hidden text-xs select-none">
      {/* Faceted Filters Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Input */}
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-2 text-zinc-500" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search entities..."
              className="bg-zinc-900 border border-zinc-800 rounded-md pl-8 pr-3 py-1 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-700 w-48 font-sans"
            />
          </div>

          {/* Type Filter Pills */}
          <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-md p-0.5">
            {["all", "mechanism", "database", "service", "team", "person"].map((t) => (
              <button
                key={t}
                onClick={() => setSelectedType(t)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono capitalize transition-colors cursor-pointer ${
                  selectedType === t
                    ? "bg-zinc-800 text-zinc-100 font-semibold"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Degree Filter */}
          <div className="hidden xl:flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
            <span>Min Degree: {minDegree}</span>
            <input
              type="range"
              min={0}
              max={10}
              value={minDegree}
              onChange={(e) => setMinDegree(Number(e.target.value))}
              className="w-16 h-1 accent-amber-500 bg-zinc-800 rounded appearance-none cursor-pointer"
            />
          </div>
        </div>

        <span className="text-[11px] font-mono text-zinc-500 tabular-nums">
          {processedNodes.length} entities (virtualized)
        </span>
      </div>

      {/* Virtualized Table Container */}
      <div className="flex-1 flex flex-col rounded-lg border border-zinc-800/80 bg-zinc-950/60 min-h-0 overflow-hidden">
        {/* Sticky Table Header */}
        <div className="grid grid-cols-12 bg-zinc-900/80 border-b border-zinc-800/80 px-3 py-2 text-[11px] font-mono text-zinc-400 shrink-0">
          <div
            className="col-span-5 flex items-center gap-1 cursor-pointer hover:text-zinc-200 transition-colors"
            onClick={() => handleSort("name")}
          >
            <span>Entity</span>
            <ArrowUpDown className="h-3 w-3 text-zinc-600" />
          </div>
          <div
            className="col-span-3 flex items-center gap-1 cursor-pointer hover:text-zinc-200 transition-colors"
            onClick={() => handleSort("type")}
          >
            <span>Type</span>
            <ArrowUpDown className="h-3 w-3 text-zinc-600" />
          </div>
          <div
            className="col-span-2 text-right flex items-center justify-end gap-1 cursor-pointer hover:text-zinc-200"
            onClick={() => handleSort("degree")}
          >
            <span>Deg</span>
            <ArrowUpDown className="h-3 w-3 text-zinc-600" />
          </div>
          <div className="col-span-2 text-center">Focus</div>
        </div>

        {/* Virtualized Body */}
        <div ref={parentRef} className="flex-1 overflow-y-auto">
          {processedNodes.length === 0 ? (
            <div className="text-center py-8 text-zinc-500 font-mono text-xs">
              No matching entities found in knowledge graph.
            </div>
          ) : (
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: "100%",
                position: "relative",
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const node = processedNodes[virtualRow.index];
                const isSelected = selectedNodeId === node.id;

                return (
                  <div
                    key={node.id}
                    onClick={() => onSelectNode(node.id)}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className={`grid grid-cols-12 items-center px-3 border-b border-zinc-800/40 text-xs transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-amber-500/10 hover:bg-amber-500/15"
                        : "hover:bg-zinc-900/60"
                    }`}
                  >
                    <div className="col-span-5 font-medium text-zinc-200 flex items-center gap-1.5 truncate">
                      {isSelected && (
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0 animate-pulse" />
                      )}
                      <span className="truncate">{node.name}</span>
                    </div>

                    <div className="col-span-3">
                      <Badge
                        variant={typeVariants[node.type] || "secondary"}
                        className="text-[9px] font-mono uppercase"
                      >
                        {node.type}
                      </Badge>
                    </div>

                    <div className="col-span-2 text-right font-mono text-zinc-300 tabular-nums">
                      {node.degree ?? 0}
                    </div>

                    <div className="col-span-2 text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectNode(node.id);
                        }}
                        className="h-6 w-6 p-0 text-zinc-400 hover:text-amber-400 hover:bg-zinc-800"
                        title="Focus on Graph"
                      >
                        <FocusIcon />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FocusIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-3 w-3"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M3 12h4m10 0h4M12 3v4m0 10v4" />
    </svg>
  );
}

export default EntityTable;

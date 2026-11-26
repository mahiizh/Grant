import { useEffect } from "react";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../components/ui/command";
import type { GraphNode } from "../types/graph";
import { Badge } from "../components/ui/badge";
import { Network, Database, Zap, Users, ArrowRight } from "lucide-react";

export interface CommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  nodes: GraphNode[];
  onSelectNode: (nodeId: string) => void;
}

export function CommandMenu({ open, onOpenChange, nodes, onSelectNode }: CommandMenuProps) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  const getIcon = (type: string) => {
    switch (type) {
      case "database":
        return <Database className="h-4 w-4 text-sky-400" />;
      case "mechanism":
        return <Zap className="h-4 w-4 text-amber-400" />;
      case "person":
      case "team":
        return <Users className="h-4 w-4 text-purple-400" />;
      default:
        return <Network className="h-4 w-4 text-emerald-400" />;
    }
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type an entity name or topic (e.g. PostgreSQL, Outbox, Alice Chen)..." />
      <CommandList>
        <CommandEmpty>No matching entities found in knowledge graph.</CommandEmpty>
        <CommandGroup heading="Graph Entities">
          {nodes.map((node) => (
            <CommandItem
              key={node.id}
              value={`${node.name} ${node.type} ${node.description}`}
              onSelect={() => {
                onSelectNode(node.id);
                onOpenChange(false);
              }}
              className="flex items-center justify-between"
            >
              <div className="flex items-center gap-2.5 truncate">
                {getIcon(node.type)}
                <span className="font-medium text-xs text-zinc-100">{node.name}</span>
                <span className="text-[11px] text-zinc-500 truncate max-w-[200px]">
                  {node.description}
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge variant="outline" className="text-[9px] uppercase font-mono py-0 px-1.5">
                  {node.type}
                </Badge>
                <ArrowRight className="h-3 w-3 text-zinc-600" />
              </div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

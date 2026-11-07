import { useEffect, useRef } from "react";
import { EnrichedNode } from "../hooks/useGraphAnalytics";
import {
  Maximize2,
  Route,
  EyeOff,
  Pin,
  Copy,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export interface NodeContextMenuProps {
  node: EnrichedNode;
  position: { x: number; y: number };
  onClose: () => void;
  onExpandNeighbors: (node: EnrichedNode) => void;
  onFindPathFromHere: (node: EnrichedNode) => void;
  onHideNode: (node: EnrichedNode) => void;
  onPinNode: (node: EnrichedNode) => void;
}

export function NodeContextMenu({
  node,
  position,
  onClose,
  onExpandNeighbors,
  onFindPathFromHere,
  onHideNode,
  onPinNode,
}: NodeContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Close on click outside or escape key
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleCopyId = () => {
    navigator.clipboard.writeText(node.id);
    toast.success(`Copied entity ID: "${node.id}"`);
    onClose();
  };

  const handleOpenDoc = () => {
    navigate(`/documents`);
    toast.info(`Inspecting source document for ${node.name}`);
    onClose();
  };

  return (
    <div
      ref={menuRef}
      style={{ top: `${position.y}px`, left: `${position.x}px` }}
      className="fixed z-50 min-w-[200px] rounded-xl border border-zinc-800 bg-zinc-950/95 backdrop-blur-md p-1.5 shadow-2xl text-xs font-sans select-none animate-in fade-in zoom-in-95 duration-100"
    >
      <div className="px-2 py-1.5 border-b border-zinc-800/80 mb-1">
        <div className="font-semibold text-zinc-100 truncate">{node.name}</div>
        <div className="text-[10px] font-mono text-zinc-500 uppercase">{node.type} · ID: {node.id}</div>
      </div>

      <div className="space-y-0.5">
        <button
          onClick={() => {
            onExpandNeighbors(node);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <Maximize2 className="h-3.5 w-3.5 text-sky-400" />
          <span>Expand neighbors</span>
        </button>

        <button
          onClick={() => {
            onFindPathFromHere(node);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <Route className="h-3.5 w-3.5 text-amber-400" />
          <span>Find path from here</span>
        </button>

        <button
          onClick={() => {
            onPinNode(node);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <Pin className="h-3.5 w-3.5 text-emerald-400" />
          <span>Pin position</span>
        </button>

        <button
          onClick={() => {
            onHideNode(node);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <EyeOff className="h-3.5 w-3.5 text-zinc-400" />
          <span>Hide node</span>
        </button>

        <div className="my-1 border-t border-zinc-800/60" />

        <button
          onClick={handleCopyId}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <Copy className="h-3.5 w-3.5 text-zinc-400" />
          <span>Copy ID</span>
        </button>

        <button
          onClick={handleOpenDoc}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900 transition-colors cursor-pointer text-left"
        >
          <FileText className="h-3.5 w-3.5 text-zinc-400" />
          <span>Open source document</span>
        </button>
      </div>
    </div>
  );
}

import { useMemo } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { CommandMenu } from "../../features/CommandMenu";
import { KeyboardShortcutsModal } from "../../features/KeyboardShortcutsModal";
import { useApp } from "../../context/AppContext";
import { useGraph } from "../../lib/api/hooks/useGraph";
import { useGraphAnalytics } from "../../hooks/useGraphAnalytics";
import { Toaster } from "sonner";

export function Shell() {
  const { commandOpen, setCommandOpen, theme } = useApp();
  const navigate = useNavigate();
  const { data: graphResponse } = useGraph();

  const graphData = useMemo(() => {
    if (!graphResponse) return { nodes: [], links: [] };
    return {
      nodes: graphResponse.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        type: n.type as any,
        description: (n as any).description || `${n.type} node`,
        valid_from: n.valid_from,
        valid_to: n.valid_to || "9999-12-31",
        tx_time: n.tx_time,
        tier: (n as any).tier || 1,
        chunkHash: (n as any).chunk_hash || "sha256:0000",
        cluster: n.community,
        pageRank: n.pagerank,
        degree: n.degree,
      })),
      links: graphResponse.links.map((l) => ({
        source: l.source,
        target: l.target,
        relation: l.label,
        tier: (l.tier as any) || 1,
        valid_from: l.valid_from,
      })),
    };
  }, [graphResponse]);

  const { nodes } = useGraphAnalytics(graphData);

  const handleSelectNode = (nodeId: string) => {
    navigate(`/graph?node=${nodeId}`);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Collapsible Left Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header />
        <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-zinc-950">
          <Outlet />
        </main>
      </div>

      {/* Global Command Menu (Cmd+K) */}
      <CommandMenu
        open={commandOpen}
        onOpenChange={setCommandOpen}
        nodes={nodes}
        onSelectNode={handleSelectNode}
      />

      {/* Global Keyboard Shortcuts Modal (?) */}
      <KeyboardShortcutsModal />

      {/* Sonner Toast Notifications */}
      <Toaster
        position="bottom-right"
        theme={theme === "light" ? "light" : "dark"}
        toastOptions={{
          className: "bg-zinc-900 border border-zinc-800 text-zinc-100 font-sans text-xs",
        }}
      />
    </div>
  );
}

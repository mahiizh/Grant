import { Outlet, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { CommandMenu } from "../../features/CommandMenu";
import { KeyboardShortcutsModal } from "../../features/KeyboardShortcutsModal";
import { useApp } from "../../context/AppContext";
import { useGraph } from "../../lib/api/hooks/useGraph";
import type { GraphNode } from "../../types/graph";
import { Toaster } from "sonner";

export function Shell() {
  const { commandOpen, setCommandOpen, theme } = useApp();
  const navigate = useNavigate();
  const { data: graphResponse } = useGraph();

  const nodes: GraphNode[] = (graphResponse?.nodes ?? []).map((n) => ({
    id: n.id,
    name: n.name,
    type: n.type as GraphNode["type"],
    description: n.name,
    source_kind: n.source_kind ?? null,
    source_kinds: n.source_kinds ?? [],
    degree: n.degree ?? 0,
    tier: 1,
    ingested_at: n.ingested_at ?? null,
  }));

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

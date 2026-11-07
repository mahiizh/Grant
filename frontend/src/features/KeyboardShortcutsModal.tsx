import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import { Keyboard } from "lucide-react";

export function KeyboardShortcutsModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // If typing in input or textarea, ignore
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const shortcuts = [
    { key: "⌘ / Ctrl + K", description: "Open global entity command search" },
    { key: "?", description: "Toggle this keyboard shortcut cheat sheet" },
    { key: "Escape", description: "Close any open dialog, sheet, or inspector" },
    { key: "Enter", description: "Submit query in Prompt Composer" },
    { key: "Shift + Enter", description: "Insert newline in prompt composer" },
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md bg-zinc-950 border-zinc-800 text-zinc-100 select-none">
        <DialogHeader>
          <div className="flex items-center gap-2 text-amber-400">
            <Keyboard className="h-5 w-5" />
            <DialogTitle className="text-sm font-semibold">
              Keyboard Shortcuts
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Quick accessibility controls and commands available across Grant Lab.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 pt-2">
          {shortcuts.map((s) => (
            <div
              key={s.key}
              className="p-2.5 rounded-lg border border-zinc-800 bg-zinc-900/50 flex items-center justify-between text-xs font-mono"
            >
              <span className="text-zinc-300 font-sans">{s.description}</span>
              <kbd className="px-2 py-0.5 rounded border border-zinc-700 bg-zinc-800 text-amber-300 text-[11px] shadow-xs">
                {s.key}
              </kbd>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

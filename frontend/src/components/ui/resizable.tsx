import * as React from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { GripVertical, GripHorizontal } from "lucide-react";
import { cn } from "../../lib/utils";

export function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof Group>) {
  return (
    <Group
      className={cn(
        "flex h-full w-full data-[panel-group-direction=vertical]:flex-col",
        className
      )}
      {...props}
    />
  );
}

export function ResizablePanel({
  className,
  ...props
}: React.ComponentProps<typeof Panel>) {
  return <Panel className={cn("overflow-hidden", className)} {...props} />;
}

export function ResizableHandle({
  withHandle,
  className,
  orientation = "horizontal",
  ...props
}: React.ComponentProps<typeof Separator> & {
  withHandle?: boolean;
  orientation?: "horizontal" | "vertical";
}) {
  return (
    <Separator
      className={cn(
        "relative flex items-center justify-center bg-zinc-800/80 transition-colors hover:bg-amber-500/50 data-[separator]:transition-all data-[separator]:cursor-col-resize data-[separator][data-orientation=vertical]:cursor-row-resize shrink-0",
        orientation === "horizontal"
          ? "w-1 hover:w-1.5 cursor-col-resize"
          : "h-1 hover:h-1.5 cursor-row-resize",
        className
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-4 w-3 items-center justify-center rounded-xs border border-zinc-700 bg-zinc-900">
          {orientation === "horizontal" ? (
            <GripVertical className="h-2.5 w-2.5 text-zinc-400" />
          ) : (
            <GripHorizontal className="h-2.5 w-2.5 text-zinc-400" />
          )}
        </div>
      )}
    </Separator>
  );
}

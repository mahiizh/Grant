import React from "react";
import { Button } from "./button";

export interface EmptyStateProps {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-zinc-800 bg-zinc-950/40 max-w-md mx-auto my-12">
      <div className="p-3.5 rounded-2xl bg-zinc-900 border border-zinc-800/80 text-zinc-400 mb-4 shadow-sm">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-base font-semibold text-zinc-100 tracking-tight">{title}</h3>
      <p className="text-xs text-zinc-400 mt-1.5 mb-6 max-w-sm leading-relaxed">
        {description}
      </p>
      {actionLabel && onAction && (
        <Button size="sm" onClick={onAction} className="text-xs font-medium">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}

import React from "react";
import { cn } from "../../lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "success" | "warning" | "destructive" | "graph" | "vector" | "cache" | "hybrid";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "border-transparent bg-zinc-100 text-zinc-900",
    secondary: "border-transparent bg-zinc-800 text-zinc-300",
    outline: "border-zinc-700 text-zinc-300",
    success: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400 font-medium",
    warning: "border-amber-500/20 bg-amber-500/10 text-amber-400 font-medium",
    destructive: "border-rose-500/20 bg-rose-500/10 text-rose-400 font-medium",
    graph: "border-purple-500/30 bg-purple-500/15 text-purple-300 font-medium",
    vector: "border-blue-500/30 bg-blue-500/15 text-blue-300 font-medium",
    cache: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300 font-medium",
    hybrid: "border-cyan-500/30 bg-cyan-500/15 text-cyan-300 font-medium",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors tracking-wide",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

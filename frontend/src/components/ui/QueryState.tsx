import React from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "./button";

interface QueryStateProps<T> {
  isLoading: boolean;
  error: Error | null;
  data: T | undefined | null;
  isEmpty?: (data: T) => boolean;
  emptyIcon?: React.ComponentType<{ className?: string }>;
  emptyTitle?: string;
  emptyDescription?: string;
  onRetry?: () => void;
  loadingSkeleton?: React.ReactNode;
  children: (data: T) => React.ReactNode;
}

export function QueryState<T>({
  isLoading,
  error,
  data,
  isEmpty,
  emptyIcon: EmptyIcon = AlertCircle,
  emptyTitle = "No records found",
  emptyDescription = "There are currently no items matching your criteria.",
  onRetry,
  loadingSkeleton,
  children,
}: QueryStateProps<T>) {
  if (isLoading) {
    if (loadingSkeleton) return <>{loadingSkeleton}</>;
    return (
      <div className="flex flex-col items-center justify-center p-8 space-y-3 min-h-[160px]">
        <div className="h-6 w-6 rounded-full border-2 border-amber-500/30 border-t-amber-400 animate-spin" />
        <span className="text-xs text-zinc-400 font-mono">Loading data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center rounded-xl border border-red-900/30 bg-red-950/20 max-w-md mx-auto my-6 space-y-3">
        <div className="p-2.5 rounded-full bg-red-900/20 text-red-400 border border-red-800/40">
          <AlertCircle className="h-5 w-5" />
        </div>
        <h3 className="text-sm font-semibold text-zinc-100">Unable to load data</h3>
        <p className="text-xs text-zinc-400 leading-relaxed font-mono">{error.message}</p>
        {onRetry && (
          <Button
            size="sm"
            variant="outline"
            onClick={onRetry}
            className="text-xs font-mono border-zinc-700 hover:bg-zinc-800"
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (!data || (isEmpty && isEmpty(data))) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 max-w-md mx-auto my-6 space-y-2">
        <div className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-500">
          <EmptyIcon className="h-5 w-5" />
        </div>
        <h3 className="text-sm font-medium text-zinc-200">{emptyTitle}</h3>
        <p className="text-xs text-zinc-400 max-w-sm">{emptyDescription}</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}

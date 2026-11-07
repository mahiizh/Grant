import React from "react";
import { cn } from "../../lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "outline" | "ghost" | "link";
  size?: "default" | "sm" | "lg" | "icon";
}

export function Button({
  className,
  variant = "default",
  size = "default",
  disabled,
  ...props
}: ButtonProps) {
  const variants = {
    default: "bg-zinc-100 text-zinc-900 hover:bg-zinc-200 active:bg-zinc-300 shadow-sm",
    secondary: "bg-zinc-800 text-zinc-100 hover:bg-zinc-700 active:bg-zinc-600",
    outline: "border border-zinc-700 bg-transparent hover:bg-zinc-800 text-zinc-200",
    ghost: "hover:bg-zinc-800 hover:text-zinc-100 text-zinc-400",
    link: "text-zinc-100 underline-offset-4 hover:underline",
  };

  const sizes = {
    default: "h-9 px-4 py-2",
    sm: "h-8 rounded-md px-3 text-xs",
    lg: "h-10 rounded-md px-8 text-base",
    icon: "h-9 w-9 p-0",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-400 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
        variants[variant],
        sizes[size],
        className
      )}
      disabled={disabled}
      {...props}
    />
  );
}

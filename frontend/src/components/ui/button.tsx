import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
}

export function Button({ variant = "primary", className = "", children, ...props }: ButtonProps) {
  let baseStyle = "rounded-lg px-4 py-2 text-sm font-semibold transition disabled:opacity-50 ";
  if (variant === "primary") baseStyle += "bg-indigo-600 text-white hover:bg-indigo-500 ";
  if (variant === "secondary") baseStyle += "border bg-white text-zinc-900 hover:bg-zinc-100 dark:bg-zinc-900 dark:text-zinc-100 ";
  if (variant === "danger") baseStyle += "bg-red-600 text-white hover:bg-red-500 ";

  return (
    <button className={baseStyle + className} {...props}>
      {children}
    </button>
  );
}

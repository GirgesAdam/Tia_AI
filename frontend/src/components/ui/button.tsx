import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-xl text-sm font-bold transition-[background-color,border-color,color,box-shadow,transform] duration-150 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 active:translate-y-px",
  {
    variants: {
      variant: {
        default: "bg-[var(--accent)] text-white shadow-[0_1px_2px_rgba(15,23,42,.08)] hover:bg-[var(--accent-strong)]",
        secondary: "border border-transparent bg-[var(--surface-2)] text-slate-800 hover:bg-[var(--surface-3)]",
        outline: "border border-[var(--border)] bg-white text-slate-700 shadow-[0_1px_1px_rgba(15,23,42,.02)] hover:border-[var(--border-strong)] hover:bg-slate-50 hover:text-slate-950",
        ghost: "text-slate-600 hover:bg-[var(--surface-2)] hover:text-slate-950",
        danger: "bg-red-600 text-white shadow-[0_1px_2px_rgba(127,29,29,.12)] hover:bg-red-700",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-5",
        icon: "size-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };

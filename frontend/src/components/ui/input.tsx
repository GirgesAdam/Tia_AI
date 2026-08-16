import * as React from "react";
import { cn } from "@/lib/utils";
export function Input({className,...props}:React.InputHTMLAttributes<HTMLInputElement>){return <input className={cn("h-11 w-full rounded-xl border border-[var(--border)] bg-white px-3 text-sm outline-none placeholder:text-slate-400 focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]",className)} {...props}/>}

import { cn } from "@/lib/utils";
const styles: Record<string,string> = {
  green:"bg-emerald-50 text-emerald-700 ring-emerald-600/20", yellow:"bg-amber-50 text-amber-700 ring-amber-600/20",
  red:"bg-red-50 text-red-700 ring-red-600/20", blue:"bg-blue-50 text-blue-700 ring-blue-600/20", gray:"bg-slate-50 text-slate-600 ring-slate-500/20",
  purple:"bg-violet-50 text-violet-700 ring-violet-600/20"
};
export function Badge({children,tone="gray",className}:{children:React.ReactNode;tone?:keyof typeof styles;className?:string}){
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",styles[tone],className)}>{children}</span>;
}

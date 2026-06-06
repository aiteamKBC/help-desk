import { cn } from "@/lib/utils";

const map: Record<string, string> = {
  Open: "bg-sky-600 text-white border-sky-600",
  Pending: "bg-amber-500 text-white border-amber-500",
  Requested: "bg-amber-500 text-white border-amber-500",
  Closed: "bg-emerald-600 text-white border-emerald-600",
  Draft: "bg-slate-600 text-white border-slate-600",
};

export const StatusBadge = ({ status, label }: { status: string; label?: string }) => (
  <span
    className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
      map[status] ?? "bg-muted text-muted-foreground border-border"
    )}
  >
    <span className="h-1.5 w-1.5 rounded-full bg-current" />
    {label || status}
  </span>
);

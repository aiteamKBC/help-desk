import { cn } from "@/lib/utils";

const map: Record<string, string> = {
  Open: "bg-[#E7F2FF] text-[#1765C1] border-[#C9E2FF]",
  Pending: "bg-[#FFF1DE] text-[#A95608] border-[#FFE0B2]",
  Requested: "bg-[#FFF1DE] text-[#A95608] border-[#FFE0B2]",
  Closed: "bg-[#E1F7E8] text-[#18733A] border-[#C4EACF]",
  Draft: "bg-slate-600 text-white border-slate-600",
};

export const StatusBadge = ({ status, label }: { status: string; label?: string }) => (
  <span
    className={cn(
      "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-medium leading-none",
      map[status] ?? "bg-muted text-muted-foreground border-border"
    )}
  >
    <span className="h-1.5 w-1.5 rounded-full bg-current" />
    {label || status}
  </span>
);

import { cn } from "@/lib/utils";

const map: Record<string, string> = {
  Open: "bg-info/10 text-info border-info/20",
  Pending: "bg-warning/10 text-warning border-warning/20",
  "In Progress": "bg-primary/10 text-primary border-primary/20",
  Resolved: "bg-success/10 text-success border-success/20",
  Closed: "bg-muted text-muted-foreground border-border",
  Draft: "bg-muted text-muted-foreground border-border",
};

export const StatusBadge = ({ status }: { status: string }) => (
  <span
    className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
      map[status] ?? "bg-muted text-muted-foreground border-border"
    )}
  >
    <span className="h-1.5 w-1.5 rounded-full bg-current" />
    {status}
  </span>
);

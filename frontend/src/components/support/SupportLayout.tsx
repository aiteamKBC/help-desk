import { Link } from "react-router-dom";
import { ReactNode } from "react";
import { KentCrestMark } from "@/components/support/KentCrestMark";
import { cn } from "@/lib/utils";

export const SupportLayout = ({
  children,
  right,
  fullWidth = false,
}: {
  children: ReactNode;
  right?: ReactNode;
  fullWidth?: boolean;
}) => (
  <div className="min-h-screen gradient-soft">
    <header className="border-b bg-card/70 backdrop-blur-sm sticky top-0 z-30">
      <div className={cn("flex h-16 items-center justify-between", fullWidth ? "w-full px-4 md:px-6" : "container")}>
        <Link to="/" className="flex items-center gap-2.5">
          <KentCrestMark className="h-14 w-[172px] shrink-0 rounded-2xl" imageClassName="p-2.5" />
          <div>
            <div className="font-semibold leading-tight">Help Desk</div>
            <div className="text-xs text-muted-foreground leading-tight">Learner Support</div>
          </div>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link to="/admin/login" className="px-3 py-1.5 rounded-lg hover:bg-secondary transition-colors">Admin</Link>
          {right}
        </nav>
      </div>
    </header>
    <main className={cn(fullWidth ? "w-full px-4 py-6 md:px-6 md:py-8" : "container py-8 md:py-10")}>{children}</main>
  </div>
);

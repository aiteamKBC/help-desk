import { LifeBuoy } from "lucide-react";
import { Link } from "react-router-dom";
import { ReactNode } from "react";

export const SupportLayout = ({ children, right }: { children: ReactNode; right?: ReactNode }) => (
  <div className="min-h-screen gradient-soft">
    <header className="border-b bg-card/70 backdrop-blur-sm sticky top-0 z-30">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-xl gradient-primary flex items-center justify-center shadow-card">
            <LifeBuoy className="h-5 w-5 text-primary-foreground" />
          </div>
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
    <main className="container py-8 md:py-10">{children}</main>
  </div>
);

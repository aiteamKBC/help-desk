import { Link, useLocation } from "react-router-dom";
import { ReactNode, useEffect, useState } from "react";
import { Menu, ShieldCheck, UserRound, X } from "lucide-react";
import { KentCrestMark } from "@/components/support/KentCrestMark";
import { cn } from "@/lib/utils";

export const SupportLayout = ({
  children,
  left,
  right,
  fullWidth = false,
  showHeader = true,
  mainClassName,
}: {
  children: ReactNode;
  left?: ReactNode;
  right?: ReactNode;
  fullWidth?: boolean;
  showHeader?: boolean;
  mainClassName?: string;
}) => {
  const location = useLocation();
  const isAdminArea = location.pathname.startsWith("/admin") || location.pathname.startsWith("/agent");
  const [isAdminMobileNavOpen, setIsAdminMobileNavOpen] = useState(false);
  const adminHeaderShellClassName = fullWidth
    ? "w-full px-4 sm:px-6 lg:px-8 xl:px-10"
    : "mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8";
  const adminPortalLink = isAdminArea ? (
    <Link
      to="/"
      className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border border-primary/12 bg-white px-3.5 py-2 text-[13px] font-medium text-foreground shadow-soft transition-all hover:border-primary/25 hover:bg-primary/5 hover:text-primary sm:text-sm"
    >
      <UserRound className="h-4 w-4 text-primary" />
      <span className="sm:hidden">Portal</span>
      <span className="hidden sm:inline">Support Portal</span>
    </Link>
  ) : null;

  useEffect(() => {
    setIsAdminMobileNavOpen(false);
  }, [location.pathname, location.search]);

  return (
    <div className="min-h-screen gradient-soft">
      {showHeader ? (
        isAdminArea ? (
          <header className="sticky top-0 z-30 border-b border-black/5 bg-white">
            <div className={cn("sm:hidden", adminHeaderShellClassName)}>
              <div className="flex min-h-[74px] items-center justify-between gap-3">
                <Link
                  to="/"
                  className="shrink-0 rounded-xl transition-opacity hover:opacity-90"
                  aria-label="Kent Business College support home"
                >
                  <KentCrestMark
                    variant="full"
                    frame="plain"
                    className="h-11 w-[170px]"
                    imageClassName="object-left"
                  />
                </Link>
                <button
                  type="button"
                  onClick={() => setIsAdminMobileNavOpen((currentState) => !currentState)}
                  aria-expanded={isAdminMobileNavOpen}
                  aria-label={isAdminMobileNavOpen ? "Close navigation menu" : "Open navigation menu"}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/12 bg-white text-primary shadow-soft transition-all hover:border-primary/25 hover:bg-primary/5"
                >
                  {isAdminMobileNavOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
                </button>
              </div>
              {isAdminMobileNavOpen ? (
                <div className="border-t border-black/5 pb-3 pt-3">
                  <div className="flex flex-col gap-2 [&_a]:w-full [&_a]:justify-start">
                    {left}
                    {adminPortalLink}
                    {right}
                  </div>
                </div>
              ) : null}
            </div>

            <div
              className={cn(
                "hidden min-h-[84px] items-center gap-3 py-3 sm:flex",
                adminHeaderShellClassName,
              )}
            >
              <Link
                to="/"
                className="shrink-0 rounded-xl transition-opacity hover:opacity-90"
                aria-label="Kent Business College support home"
              >
                <KentCrestMark
                  variant="full"
                  frame="plain"
                  className="h-12 w-[176px] lg:h-[52px] lg:w-[188px]"
                  imageClassName="object-left"
                />
              </Link>

              {left ? (
                <div className="flex items-center gap-1.5">
                  {left}
                </div>
              ) : null}

              <div className="ml-auto flex items-center gap-2">
                {adminPortalLink}
                {right}
              </div>
            </div>
          </header>
        ) : (
          <header className="sticky top-0 z-30 border-b border-black/5 bg-white">
            <div
              className={cn(
                "flex min-h-[78px] items-center gap-3 sm:min-h-[84px] sm:gap-4",
                fullWidth ? "w-full px-4 md:px-6" : "mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8",
              )}
            >
              <Link
                to="/"
                className="shrink-0 rounded-xl transition-opacity hover:opacity-90"
                aria-label="Kent Business College support home"
              >
                <KentCrestMark
                  variant="full"
                  frame="plain"
                  className="h-11 w-[176px] sm:h-12 sm:w-[210px] lg:h-[54px] lg:w-[235px]"
                  imageClassName="object-left"
                />
              </Link>

              {left ? <div className="flex items-center gap-2">{left}</div> : null}

              <div className="ml-auto flex items-center gap-2">
                <Link
                  to="/admin/login"
                  className="inline-flex items-center gap-2 rounded-full bg-primary px-3.5 py-2 text-[13px] font-semibold text-primary-foreground shadow-card transition-all hover:opacity-95 sm:text-sm"
                >
                  <ShieldCheck className="h-4 w-4" />
                  <span>Admin</span>
                </Link>
                {right}
              </div>
            </div>
          </header>
        )
      ) : null}
      <main
        className={cn(
          fullWidth
            ? (isAdminArea ? "w-full px-4 py-5 sm:px-6 md:px-8 md:py-8 xl:px-10" : "w-full px-4 py-6 md:px-6 md:py-8")
            : "container py-8 md:py-10",
          mainClassName,
        )}
      >
        {children}
      </main>
    </div>
  );
};

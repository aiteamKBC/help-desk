import { Link, useLocation } from "react-router-dom";
import { ReactNode, useEffect, useState } from "react";
import { BookOpen, Menu, ShieldCheck, UserRound, X } from "lucide-react";
import { KentCrestMark } from "@/components/support/KentCrestMark";
import {
  adminPortalReturnQueryParam,
  canReturnToAdminDashboard,
  syncAdminPortalReturnFromSearch,
} from "@/lib/adminSession";
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
  const isKnowledgeBaseArea = location.pathname.startsWith("/knowledge-base");
  const isAdminDashboardArea = location.pathname === "/admin" || location.pathname === "/agent";
  const isAdminArea =
    location.pathname.startsWith("/admin") ||
    location.pathname.startsWith("/agent") ||
    isKnowledgeBaseArea;
  const [isAdminMobileNavOpen, setIsAdminMobileNavOpen] = useState(false);
  const [showAdminReturnLink, setShowAdminReturnLink] = useState(() => !isAdminArea && canReturnToAdminDashboard());
  const effectiveShowHeader = showHeader;
  const adminHeaderShellClassName = fullWidth
    ? "w-full px-4 sm:px-6 lg:px-8 xl:px-10"
    : "mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8";
  const internalLinkClassName = (active: boolean) =>
    cn(
      "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 text-[13px] font-medium shadow-soft transition-all sm:text-sm",
      active
        ? "border-primary/18 bg-primary/10 text-primary"
        : "border-primary/12 bg-white text-foreground hover:border-primary/25 hover:bg-primary/5 hover:text-primary",
    );
  const knowledgeBaseLink = (
    <Link to="/knowledge-base" className={internalLinkClassName(isKnowledgeBaseArea)}>
      <BookOpen className="h-4 w-4 text-primary" />
      <span className="sm:hidden">KB</span>
      <span className="hidden sm:inline">Knowledge Base</span>
    </Link>
  );
  const adminDashboardLink = isKnowledgeBaseArea ? (
    <Link to="/admin" className={internalLinkClassName(false)}>
      <ShieldCheck className="h-4 w-4 text-primary" />
      <span className="sm:hidden">Admin</span>
      <span className="hidden sm:inline">Admin Dashboard</span>
    </Link>
  ) : null;
  const adminReturnLink = showAdminReturnLink ? (
    <Link to="/admin" className={internalLinkClassName(false)}>
      <ShieldCheck className="h-4 w-4 text-primary" />
      <span className="sm:hidden">Admin</span>
      <span className="hidden sm:inline">Admin</span>
    </Link>
  ) : null;
  const adminPortalLink = isAdminArea ? (
    <Link
      to={{
        pathname: "/",
        search: `?${adminPortalReturnQueryParam}=1`,
      }}
      className={internalLinkClassName(!isKnowledgeBaseArea)}
    >
      <UserRound className="h-4 w-4 text-primary" />
      <span className="sm:hidden">Portal</span>
      <span className="hidden sm:inline">Support Portal</span>
    </Link>
  ) : null;
  const publicAdminPortalLink = !isAdminArea && !showAdminReturnLink ? (
    <Link to="/admin" className={internalLinkClassName(false)}>
      <ShieldCheck className="h-4 w-4 text-primary" />
      <span className="sm:hidden">Admin</span>
      <span className="hidden sm:inline">Admin</span>
    </Link>
  ) : null;

  useEffect(() => {
    syncAdminPortalReturnFromSearch(location.search);
    setShowAdminReturnLink(!isAdminArea && canReturnToAdminDashboard());
    setIsAdminMobileNavOpen(false);
  }, [isAdminArea, location.pathname, location.search]);

  return (
    <div className="min-h-screen gradient-soft">
      {effectiveShowHeader ? (
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
                    {isAdminDashboardArea ? knowledgeBaseLink : null}
                    {adminDashboardLink}
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
                {isAdminDashboardArea ? knowledgeBaseLink : null}
                {adminDashboardLink}
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
                {adminReturnLink}
                {right}
                {publicAdminPortalLink}
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

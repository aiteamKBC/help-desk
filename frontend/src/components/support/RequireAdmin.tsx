import { Navigate } from "react-router-dom";
import { ReactNode, useEffect, useState } from "react";
import { clearAdminSession, fetchVerifiedAdminSession, getAdminSession, setAdminSession } from "@/lib/adminSession";

export const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const [redirectTarget, setRedirectTarget] = useState<"/admin/login" | "/support" | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    async function validateAdminSession() {
      const cachedSession = getAdminSession();
      const cachedRole = (cachedSession?.role || "").trim().toLowerCase();
      const canUseCachedAdminSession = cachedRole === "admin" || cachedRole === "superadmin";

      try {
        const { response, admin } = await fetchVerifiedAdminSession(controller.signal);
        if (response.status === 401) {
          clearAdminSession();
          setRedirectTarget("/admin/login");
          return;
        }

        if (response.status === 403) {
          clearAdminSession();
          setRedirectTarget("/support");
          return;
        }

        if (!response.ok) {
          if (canUseCachedAdminSession) {
            setRedirectTarget(null);
            return;
          }

          clearAdminSession();
          setRedirectTarget("/admin/login");
          return;
        }

        const normalizedRole = (admin?.role || "").trim().toLowerCase();

        if (!admin) {
          clearAdminSession();
          setRedirectTarget("/admin/login");
          return;
        }

        if (normalizedRole !== "admin" && normalizedRole !== "superadmin") {
          clearAdminSession();
          setRedirectTarget("/support");
          return;
        }

        setAdminSession(admin);
        setRedirectTarget(null);
      } catch {
        if (!controller.signal.aborted) {
          if (canUseCachedAdminSession) {
            setRedirectTarget(null);
          } else {
            clearAdminSession();
            setRedirectTarget("/admin/login");
          }
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsCheckingSession(false);
        }
      }
    }

    void validateAdminSession();

    return () => controller.abort();
  }, []);

  if (isCheckingSession) {
    return null;
  }

  if (redirectTarget) {
    return <Navigate to={redirectTarget} replace />;
  }

  return <>{children}</>;
};

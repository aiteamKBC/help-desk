import { Navigate } from "react-router-dom";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { clearAdminSession, fetchVerifiedAdminSession, getAdminSession, setAdminSession } from "@/lib/adminSession";

const defaultAllowedRoles = ["admin", "superadmin"] as const;

interface RequireAdminProps {
  children: ReactNode;
  allowedRoles?: readonly string[];
}

function buildAllowedRoleSet(allowedRoles: readonly string[]) {
  return new Set(allowedRoles.map((role) => role.trim().toLowerCase()).filter(Boolean));
}

export const RequireAdmin = ({ children, allowedRoles = defaultAllowedRoles }: RequireAdminProps) => {
  const [redirectTarget, setRedirectTarget] = useState<"/admin/login" | "/support" | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const allowedRoleSet = useMemo(() => buildAllowedRoleSet(allowedRoles), [allowedRoles]);

  useEffect(() => {
    const controller = new AbortController();

    async function validateAdminSession() {
      const cachedSession = getAdminSession();
      const cachedRole = (cachedSession?.role || "").trim().toLowerCase();
      const canUseCachedAdminSession = allowedRoleSet.has(cachedRole);

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

        if (!allowedRoleSet.has(normalizedRole)) {
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
  }, [allowedRoleSet]);

  if (isCheckingSession) {
    return null;
  }

  if (redirectTarget) {
    return <Navigate to={redirectTarget} replace />;
  }

  return <>{children}</>;
};

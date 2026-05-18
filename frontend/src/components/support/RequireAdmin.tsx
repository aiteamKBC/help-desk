import { Navigate } from "react-router-dom";
import { ReactNode } from "react";
import { getAdminSession } from "@/lib/adminSession";

export const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const session = getAdminSession();
  const normalizedRole = (session?.role || "").trim().toLowerCase();
  if (!session) return <Navigate to="/admin/login" replace />;
  if (normalizedRole !== "admin" && normalizedRole !== "superadmin") {
    return <Navigate to="/support" replace />;
  }
  return <>{children}</>;
};

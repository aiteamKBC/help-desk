import { Navigate } from "react-router-dom";
import { ReactNode } from "react";
import { getAdminSession } from "@/lib/adminSession";

export const RequireAdmin = ({ children }: { children: ReactNode }) => {
  const session = getAdminSession();
  if (!session) return <Navigate to="/admin/login" replace />;
  return <>{children}</>;
};

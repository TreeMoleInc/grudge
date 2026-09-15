import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) return null; // avoid a flash-redirect while /me is still in flight
  if (!user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "../api/auth";
import { AuthContext, ME_QUERY_KEY, type AuthContextValue } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // A 401 here means "logged out," an expected steady state for a visitor -
  // retry:false so it isn't treated as a transient failure worth backing off
  // on, and query errors never throw by default (React Query only throws
  // when throwOnError is explicitly set), so a 401 just leaves `data`
  // undefined rather than crashing the app.
  const { data, isLoading } = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    retry: false,
  });

  const value: AuthContextValue = {
    user: data ?? null,
    isLoading,
    refetch: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

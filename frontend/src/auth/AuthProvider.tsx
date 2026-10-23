import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "../api/auth";
import { ApiError } from "../api/client";
import type { UserRead } from "../api/types";
import { AuthContext, ME_QUERY_KEY, type AuthContextValue } from "./AuthContext";

// "Not logged in" is a normal, expected state for a visitor - not a failure.
// Treating the 401 as a query *error* made React Query put the query back into
// its "pending" (loading) state on every background refetch (a tab regaining
// focus, the network reconnecting), because an errored query has no data to
// keep showing. HomePage and RequireAuth render nothing while loading, so a
// logged-out visitor saw the whole page blank out and reappear every time they
// returned to the tab. Resolving a 401 to `null` makes "logged out" a real
// answer, which a refetch simply re-confirms - no loading state in between.
// (AccountPanel's logout/delete already write `null` into this same cache
// entry, so null was already the cache's "logged out" value.)
async function fetchMeOrNull(): Promise<UserRead | null> {
  try {
    return await fetchMe();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // retry:false so a genuine failure (server down) isn't backed off on.
  const { data, isPending, dataUpdatedAt, errorUpdatedAt } = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMeOrNull,
    retry: false,
  });

  const value: AuthContextValue = {
    user: data ?? null,
    // Only the very first load counts as "loading". Backstop for the case the
    // 401 handling above doesn't cover (a real network/server error): that
    // query still flips back to pending on every refetch, but it has already
    // settled once (errorUpdatedAt is set and survives the refetch), so the
    // page keeps rendering instead of blanking out again.
    isLoading: isPending && dataUpdatedAt === 0 && errorUpdatedAt === 0,
    refetch: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

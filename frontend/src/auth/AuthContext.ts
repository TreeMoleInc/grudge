import { createContext } from "react";
import type { UserRead } from "../api/types";

export interface AuthContextValue {
  user: UserRead | null;
  isLoading: boolean;
  refetch: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const ME_QUERY_KEY = ["me"] as const;

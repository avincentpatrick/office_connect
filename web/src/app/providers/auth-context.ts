import { createContext, useContext } from "react";
import type { MeResponse } from "../../api/types";

export const ME_QUERY_KEY = ["me"] as const;

export interface AuthState {
  me: MeResponse | null;
  isLoading: boolean;
}

/** Exported for tests — app code uses <AuthProvider> + useAuth(). */
export const AuthContext = createContext<AuthState>({ me: null, isLoading: false });

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "../../api/auth";
import { ApiError } from "../../api/http";
import type { MeResponse } from "../../api/types";
import { AuthContext, ME_QUERY_KEY } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const { data, isPending } = useQuery({
    queryKey: ME_QUERY_KEY,
    // 401 means "not signed in" — a state, not an error.
    queryFn: async (): Promise<MeResponse | null> => {
      try {
        return await fetchMe();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  return (
    <AuthContext.Provider value={{ me: data ?? null, isLoading: isPending }}>
      {children}
    </AuthContext.Provider>
  );
}

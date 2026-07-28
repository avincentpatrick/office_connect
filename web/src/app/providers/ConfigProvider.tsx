import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchConfig } from "../../api/config";
import { injectTokens } from "../../theme/tokens";
import { PageSkeleton } from "../../components/Skeleton/Skeleton";
import { ConfigContext, FALLBACK_CONFIG } from "./config-context";

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { data, isPending } = useQuery({
    queryKey: ["config"],
    queryFn: fetchConfig,
    staleTime: 30_000, // matches the backend's Redis cache TTL
    retry: 1,
  });

  useEffect(() => {
    if (data) injectTokens(data.tokens);
  }, [data]);

  // Block the first meaningful paint on the config fetch (fast: public,
  // Redis-cached, never 500s) so tenant branding lands before the app renders.
  if (isPending) return <PageSkeleton label="Loading Office-Connect" />;

  return <ConfigContext.Provider value={data ?? FALLBACK_CONFIG}>{children}</ConfigContext.Provider>;
}

import { createContext, useContext } from "react";
import type { ConfigResponse } from "../../api/types";

/**
 * Fail-safe fallback when /api/v1/config is unreachable after retry: neutral
 * tokens (the baked :root block in tokens.css) and features = {} (all OFF),
 * mirroring the backend's own degraded-config contract.
 */
export const FALLBACK_CONFIG: ConfigResponse = {
  tenant: { name: "Office-Connect", short_name: "OC", timezone: "Asia/Manila" },
  branding: {},
  tokens: {},
  features: {},
  version: "",
};

export const ConfigContext = createContext<ConfigResponse>(FALLBACK_CONFIG);

export function useConfig(): ConfigResponse {
  return useContext(ConfigContext);
}

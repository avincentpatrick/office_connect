import { api } from "./http";
import type { ConfigResponse } from "./types";

export function fetchConfig(): Promise<ConfigResponse> {
  return api<ConfigResponse>("/config");
}

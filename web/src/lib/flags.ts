/**
 * Feature flags come from GET /api/v1/config `features`. The backend contract
 * is fail-safe OFF: an ABSENT key means the feature is OFF — never default on.
 */
export function isFeatureOn(features: Record<string, boolean>, key: string): boolean {
  return features[key] === true;
}

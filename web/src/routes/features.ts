export const FEATURE_FLAGS = {
  digest: true,
  admin: true,
} as const;

export type FeatureFlag = keyof typeof FEATURE_FLAGS;

export function isFeatureEnabled(flag: FeatureFlag | undefined): boolean {
  return flag === undefined || FEATURE_FLAGS[flag];
}

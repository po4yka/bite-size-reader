import { useEffect, type ReactNode } from "react";

export type ThemeName = "white" | "g100" | "g90" | "g10" | "light" | "dark";

export interface ThemeProps {
  theme?: ThemeName;
  children?: ReactNode;
}

function mapThemeName(theme: ThemeName | undefined): "light" | "dark" {
  if (theme === "g100" || theme === "g90" || theme === "dark") return "dark";
  return "light";
}

/**
 * Project shim for Carbon's `<Theme>` provider.
 *
 * Accepts both the legacy Carbon vocabulary (`"white" | "g100"` etc.) AND the
 * new project vocabulary (`"light" | "dark"`). The chosen value is written to
 * `document.documentElement.dataset.theme` so token CSS selectors
 * (`[data-theme="dark"] { ... }`) take effect on first paint.
 *
 * The shim renders children inline (no wrapper element) so existing callers
 * relying on Carbon's wrapper-less behaviour stay unaffected.
 */
export function Theme({ theme, children }: ThemeProps) {
  const mapped = mapThemeName(theme);
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = mapped;
  }, [mapped]);
  return <>{children}</>;
}

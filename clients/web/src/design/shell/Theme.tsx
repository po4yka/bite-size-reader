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

/** Project theme provider for writing the active light/dark token mode. */
export function Theme({ theme, children }: ThemeProps) {
  const mapped = mapThemeName(theme);
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = mapped;
  }, [mapped]);
  return <>{children}</>;
}

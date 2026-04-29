import type { SVGAttributes } from "react";

export interface IconProps extends SVGAttributes<SVGSVGElement> {
  size?: number | string;
  /** Carbon `aria-label` parity. */
  "aria-label"?: string;
}

export const ICON_DEFAULTS = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.25,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

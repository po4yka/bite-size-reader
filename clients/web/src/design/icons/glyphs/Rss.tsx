import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Rss = forwardRef<SVGSVGElement, IconProps>(function Rss(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M3 3a10 10 0 0 1 10 10" />
      <path d="M3 7a6 6 0 0 1 6 6" />
      <circle cx="4" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
});

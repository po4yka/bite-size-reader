import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Settings = forwardRef<SVGSVGElement, IconProps>(function Settings(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.5v2M8 12.5v2M2.5 8h2M11.5 8h2M3.7 3.7l1.4 1.4M10.9 10.9l1.4 1.4M3.7 12.3l1.4-1.4M10.9 5.1l1.4-1.4" />
    </svg>
  );
});

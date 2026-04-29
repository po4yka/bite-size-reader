import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const StopFilled = forwardRef<SVGSVGElement, IconProps>(
  function StopFilled({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <rect x="4" y="4" width="8" height="8" fill="currentColor" />
      </svg>
    );
  },
);

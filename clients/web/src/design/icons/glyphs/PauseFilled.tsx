import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const PauseFilled = forwardRef<SVGSVGElement, IconProps>(
  function PauseFilled({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <rect x="4" y="3" width="2.5" height="10" fill="currentColor" />
        <rect x="9.5" y="3" width="2.5" height="10" fill="currentColor" />
      </svg>
    );
  },
);

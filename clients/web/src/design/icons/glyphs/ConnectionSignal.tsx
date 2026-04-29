import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const ConnectionSignal = forwardRef<SVGSVGElement, IconProps>(
  function ConnectionSignal({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <path d="M2 13h2v-2H2zM6 13h2V9H6zM10 13h2V6h-2zM14 13V3" />
      </svg>
    );
  },
);

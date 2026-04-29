import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const DataBackup = forwardRef<SVGSVGElement, IconProps>(
  function DataBackup({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <ellipse cx="8" cy="4" rx="5" ry="1.75" />
        <path d="M3 4v8c0 1 2.2 1.75 5 1.75s5-.75 5-1.75V4" />
        <path d="M3 8c0 1 2.2 1.75 5 1.75s5-.75 5-1.75" />
      </svg>
    );
  },
);

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const DocumentImport = forwardRef<SVGSVGElement, IconProps>(
  function DocumentImport({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <path d="M9 2H4v12h8V5z" />
        <path d="M9 2v3h3" />
        <path d="M8 7v5M5.5 9.5L8 12l2.5-2.5" />
      </svg>
    );
  },
);

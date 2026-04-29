import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Catalog = forwardRef<SVGSVGElement, IconProps>(function Catalog(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <rect x="2.5" y="2.5" width="11" height="11" rx="1" />
      <path d="M5 5h6M5 8h6M5 11h4" />
    </svg>
  );
});

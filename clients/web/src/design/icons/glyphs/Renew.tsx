import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Renew = forwardRef<SVGSVGElement, IconProps>(function Renew(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M13 8a5 5 0 1 1-1.5-3.5" />
      <path d="M13 2v3h-3" />
    </svg>
  );
});

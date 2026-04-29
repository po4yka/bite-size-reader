import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Checkmark = forwardRef<SVGSVGElement, IconProps>(function Checkmark(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M3 8.5l3.2 3.2L13 4.8" />
    </svg>
  );
});

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const TrashCan = forwardRef<SVGSVGElement, IconProps>(function TrashCan(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M3 4h10M6.5 4V2.5h3V4M4 4l1 9.5h6L12 4" />
      <path d="M6.5 6.5v5M9.5 6.5v5" />
    </svg>
  );
});

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Edit = forwardRef<SVGSVGElement, IconProps>(function Edit(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M11 2.5l2.5 2.5L6 12.5H3.5V10z" />
      <path d="M9 4.5l2.5 2.5" />
    </svg>
  );
});

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Lightning = forwardRef<SVGSVGElement, IconProps>(function Lightning(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M9 2L4 9h3l-1 5 5-7H8l1-5z" />
    </svg>
  );
});

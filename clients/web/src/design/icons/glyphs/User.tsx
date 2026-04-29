import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const User = forwardRef<SVGSVGElement, IconProps>(function User(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <circle cx="8" cy="6" r="3" />
      <path d="M2.5 14a5.5 5.5 0 0 1 11 0" />
    </svg>
  );
});

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Logout = forwardRef<SVGSVGElement, IconProps>(function Logout(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M9 3H3v10h6" />
      <path d="M11 5l3 3-3 3M14 8H6" />
    </svg>
  );
});

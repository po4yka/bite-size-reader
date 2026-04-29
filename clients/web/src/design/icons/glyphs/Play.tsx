import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Play = forwardRef<SVGSVGElement, IconProps>(function Play(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M5 3v10l8-5z" fill="currentColor" />
    </svg>
  );
});

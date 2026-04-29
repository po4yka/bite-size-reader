import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Tag = forwardRef<SVGSVGElement, IconProps>(function Tag(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M2.5 2.5h5l6 6-5 5-6-6z" />
      <circle cx="5" cy="5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  );
});

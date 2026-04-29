import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Search = forwardRef<SVGSVGElement, IconProps>(function Search(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <circle cx="7" cy="7" r="4" />
      <path d="M10 10l3.5 3.5" />
    </svg>
  );
});

import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Book = forwardRef<SVGSVGElement, IconProps>(function Book(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M3 3h7a2 2 0 0 1 2 2v8H5a2 2 0 0 0-2 2V3z" />
      <path d="M3 3v12" />
    </svg>
  );
});

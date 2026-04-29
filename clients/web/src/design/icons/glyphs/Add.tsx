import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Add = forwardRef<SVGSVGElement, IconProps>(function Add(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg
      ref={ref}
      {...ICON_DEFAULTS}
      width={size}
      height={size}
      role="img"
      {...rest}
    >
      <circle cx="8" cy="8" r="6" />
      <path d="M8 5v6M5 8h6" />
    </svg>
  );
});

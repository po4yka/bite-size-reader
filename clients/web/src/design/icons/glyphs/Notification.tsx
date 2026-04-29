import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Notification = forwardRef<SVGSVGElement, IconProps>(
  function Notification({ size = 16, ...rest }, ref) {
    return (
      <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
        <path d="M3 12V8a5 5 0 0 1 10 0v4l1 1H2z" />
        <path d="M6.5 13.5a1.5 1.5 0 0 0 3 0" />
      </svg>
    );
  },
);

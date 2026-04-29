import { forwardRef } from "react";
import { ICON_DEFAULTS, type IconProps } from "../types";

export const Close = forwardRef<SVGSVGElement, IconProps>(function Close(
  { size = 16, ...rest },
  ref,
) {
  return (
    <svg ref={ref} {...ICON_DEFAULTS} width={size} height={size} role="img" {...rest}>
      <path d="M3 3l10 10M13 3L3 13" />
    </svg>
  );
});

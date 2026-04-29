import { forwardRef, type HTMLAttributes, type ReactNode } from "react";

export interface TileProps extends HTMLAttributes<HTMLDivElement> {
  light?: boolean;
  children?: ReactNode;
}

export const Tile = forwardRef<HTMLDivElement, TileProps>(function Tile(
  { light: _light, className, children, ...rest },
  ref,
) {
  void _light;
  const cls = ["rtk-tile", className].filter(Boolean).join(" ");
  return (
    <div ref={ref} className={cls} {...rest}>
      {children}
    </div>
  );
});

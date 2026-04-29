import type { HTMLAttributes, ReactNode } from "react";

export interface ButtonSetProps extends HTMLAttributes<HTMLDivElement> {
  stacked?: boolean;
  children?: ReactNode;
}

export function ButtonSet({
  stacked = false,
  className,
  children,
  ...rest
}: ButtonSetProps) {
  const cls = [
    "rtk-button-set",
    stacked ? "rtk-button-set--stacked" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}

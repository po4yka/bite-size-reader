import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  align?: "top" | "bottom" | "left" | "right";
  kind?: "primary" | "secondary" | "tertiary" | "ghost";
  size?: "sm" | "md" | "lg";
  children?: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { label, align: _align, kind = "ghost", size = "md", className, children, ...rest },
    ref,
  ) {
    void _align;
    const cls = [
      "rtk-icon-button",
      `rtk-icon-button--${kind}`,
      `rtk-icon-button--${size}`,
      className,
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <button
        ref={ref}
        type="button"
        className={cls}
        aria-label={label}
        title={label}
        {...rest}
      >
        {children}
      </button>
    );
  },
);

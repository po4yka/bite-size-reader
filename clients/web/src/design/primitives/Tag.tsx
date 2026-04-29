import { forwardRef, type HTMLAttributes, type ReactNode } from "react";

export type TagType =
  | "red"
  | "magenta"
  | "purple"
  | "blue"
  | "cyan"
  | "teal"
  | "green"
  | "gray"
  | "cool-gray"
  | "warm-gray"
  | "high-contrast"
  | "outline";

export type TagSize = "sm" | "md" | "lg";

export interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  type?: TagType;
  size?: TagSize;
  filter?: boolean;
  onClose?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  children?: ReactNode;
}

export const Tag = forwardRef<HTMLSpanElement, TagProps>(function Tag(
  {
    type = "gray",
    size = "md",
    filter = false,
    onClose,
    disabled = false,
    className,
    children,
    ...rest
  },
  ref,
) {
  const cls = [
    "rtk-tag",
    `rtk-tag--${type}`,
    `rtk-tag--${size}`,
    disabled ? "rtk-tag--disabled" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span ref={ref} className={cls} {...rest}>
      <span className="rtk-tag__label">{children}</span>
      {filter ? (
        <button
          type="button"
          className="rtk-tag__close"
          onClick={onClose}
          disabled={disabled}
          aria-label="Clear filter"
        >
          ×
        </button>
      ) : null}
    </span>
  );
});

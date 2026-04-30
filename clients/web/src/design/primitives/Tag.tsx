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

/** Frost Chip — bracketed uppercase mono label. [ LABEL ]
 *
 * The legacy Carbon color enum (type prop) collapses to default | critical:
 * - "red" maps to critical (spark hairline)
 * - all other values resolve to default
 * A dev-mode deprecation warning is logged for any non-default, non-red type.
 */
export const Tag = forwardRef<HTMLSpanElement, TagProps>(function Tag(
  {
    type = "gray",
    size: _size,
    filter = false,
    onClose,
    disabled = false,
    className,
    style,
    children,
    ...rest
  },
  ref,
) {
  void _size;

  const isCritical = type === "red";

  if (
    import.meta.env.DEV &&
    type !== "gray" &&
    type !== "red"
  ) {
    console.warn(
      `[Tag] The "${type}" type is deprecated in Frost. ` +
        `Use type="gray" (default) or type="red" (critical) instead. ` +
        `All non-critical color variants have been removed.`,
    );
  }

  const cls = [
    "frost-chip",
    isCritical ? "frost-chip--critical" : null,
    disabled ? "frost-chip--disabled" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      ref={ref}
      className={cls}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--frost-gap-inline)",
        fontFamily: "var(--frost-font-mono)",
        fontSize: "var(--frost-type-mono-xs-size)",
        fontWeight: 800,
        letterSpacing: "var(--frost-type-mono-xs-tracking)",
        lineHeight: "var(--frost-type-mono-xs-line-height)",
        textTransform: "uppercase",
        color: "var(--frost-ink)",
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? "not-allowed" : "default",
        ...style,
      }}
      {...rest}
    >
      <span
        style={{
          border: isCritical
            ? "var(--frost-hairline) solid var(--frost-spark)"
            : "var(--frost-hairline) solid var(--frost-ink)",
          borderRadius: 0,
          padding: "2px 6px",
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--frost-gap-inline)",
        }}
      >
        {children}
        {filter ? (
          <button
            type="button"
            onClick={onClose}
            disabled={disabled}
            aria-label="Clear filter"
            style={{
              background: "none",
              border: "none",
              padding: 0,
              margin: 0,
              cursor: disabled ? "not-allowed" : "pointer",
              fontFamily: "inherit",
              fontSize: "inherit",
              fontWeight: "inherit",
              color: "inherit",
              lineHeight: 1,
            }}
          >
            ×
          </button>
        ) : null}
      </span>
    </span>
  );
});

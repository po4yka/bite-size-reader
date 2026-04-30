import type { HTMLAttributes, LiHTMLAttributes, ReactNode } from "react";

export interface UnorderedListProps extends HTMLAttributes<HTMLUListElement> {
  nested?: boolean;
  isExpressive?: boolean;
  children?: ReactNode;
}

export function UnorderedList({
  nested: _nested,
  isExpressive: _isExpressive,
  className,
  style,
  children,
  ...rest
}: UnorderedListProps) {
  void _nested;
  void _isExpressive;
  return (
    <ul
      className={className}
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        fontFamily: "var(--frost-font-mono)",
        fontSize: "13px",
        fontWeight: 500,
        lineHeight: "130%",
        letterSpacing: "0.4px",
        ...style,
      }}
      {...rest}
    >
      {children}
    </ul>
  );
}

export interface ListItemProps extends LiHTMLAttributes<HTMLLIElement> {
  /** Nesting depth — each level indents by 24px. */
  depth?: number;
  children?: ReactNode;
}

export function ListItem({ className, style, children, depth = 0, ...rest }: ListItemProps) {
  return (
    <li
      className={className}
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: "6px",
        paddingLeft: depth * 24,
        ...style,
      }}
      {...rest}
    >
      {/* mono dot leader at alpha 0.4 */}
      <span
        aria-hidden
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "13px",
          opacity: 0.4,
          flexShrink: 0,
          userSelect: "none",
        }}
      >
        ·
      </span>
      <span>{children}</span>
    </li>
  );
}

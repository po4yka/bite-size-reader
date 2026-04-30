import type { HTMLAttributes, ReactNode } from "react";

/* ─── RowDigest — Frost replacement for StructuredList ──────────────────────── *
 *
 * Single-row mono cells separated by · glyph at alpha 0.4.
 * Layout: flex row, gap = var(--frost-gap-inline) (4px),
 * separator pseudo-elements between non-first children.
 *
 * Multi-component API (Wrapper, Head, Body, Row, Cell) preserved so Phase 3
 * imports are mechanical.
 */

const ROW_DIVIDER = "color-mix(in oklch, var(--frost-ink) 50%, transparent)";

/* ─── Wrapper ────────────────────────────────────────────────────────────────── */

export interface StructuredListWrapperProps extends HTMLAttributes<HTMLDivElement> {
  ariaLabel?: string;
  isCondensed?: boolean;
  isFlush?: boolean;
  selection?: boolean;
  children?: ReactNode;
}

export function StructuredListWrapper({
  ariaLabel,
  isCondensed: _isCondensed,
  isFlush: _isFlush,
  selection: _selection,
  className,
  style,
  children,
  ...rest
}: StructuredListWrapperProps) {
  void _isCondensed;
  void _isFlush;
  void _selection;
  return (
    <div
      role="table"
      aria-label={ariaLabel}
      className={["frost-row-digest", className].filter(Boolean).join(" ")}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "var(--frost-type-mono-body-size)",
        fontWeight: "var(--frost-type-mono-body-weight)" as React.CSSProperties["fontWeight"],
        letterSpacing: "var(--frost-type-mono-body-tracking)",
        color: "var(--frost-ink)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

/* ─── Alias: RowDigestWrapper (Frost name) ───────────────────────────────────── */
export { StructuredListWrapper as RowDigestWrapper };

/* ─── Head ───────────────────────────────────────────────────────────────────── */

export interface StructuredListHeadProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function StructuredListHead({
  className,
  style,
  children,
  ...rest
}: StructuredListHeadProps) {
  return (
    <div
      role="rowgroup"
      className={["frost-row-digest__head", className].filter(Boolean).join(" ")}
      style={{
        borderBottom: `1px solid ${ROW_DIVIDER}`,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export { StructuredListHead as RowDigestHead };

/* ─── Body ───────────────────────────────────────────────────────────────────── */

export interface StructuredListBodyProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function StructuredListBody({
  className,
  children,
  ...rest
}: StructuredListBodyProps) {
  return (
    <div
      role="rowgroup"
      className={["frost-row-digest__body", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export { StructuredListBody as RowDigestBody };

/* ─── Row ─────────────────────────────────────────────────────────────────────── */

export interface StructuredListRowProps extends HTMLAttributes<HTMLDivElement> {
  head?: boolean;
  label?: boolean;
  tabIndex?: number;
  children?: ReactNode;
}

export function StructuredListRow({
  head: _head,
  label: _label,
  className,
  style,
  children,
  ...rest
}: StructuredListRowProps) {
  void _head;
  void _label;
  return (
    <div
      role="row"
      className={["frost-row-digest__row", className].filter(Boolean).join(" ")}
      style={{
        display: "flex",
        flexDirection: "row",
        alignItems: "baseline",
        gap: "var(--frost-gap-inline)",
        padding: "8px 0",
        borderBottom: `1px solid ${ROW_DIVIDER}`,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export { StructuredListRow as RowDigestRow };

/* ─── Cell ────────────────────────────────────────────────────────────────────── */

export interface StructuredListCellProps extends HTMLAttributes<HTMLDivElement> {
  head?: boolean;
  noWrap?: boolean;
  /** When true this cell is the active/primary cell (alpha 1.0). Default: false (alpha 0.55). */
  active?: boolean;
  children?: ReactNode;
}

export function StructuredListCell({
  head = false,
  noWrap: _noWrap,
  active = false,
  className,
  style,
  children,
  ...rest
}: StructuredListCellProps) {
  void _noWrap;
  return (
    <div
      role={head ? "columnheader" : "cell"}
      className={[
        "frost-row-digest__cell",
        head ? "frost-row-digest__cell--head" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: head ? "var(--frost-type-mono-xs-size)" : "var(--frost-type-mono-body-size)",
        fontWeight: head ? 800 : ("var(--frost-type-mono-body-weight)" as React.CSSProperties["fontWeight"]),
        letterSpacing: head ? "var(--frost-type-mono-xs-tracking)" : "var(--frost-type-mono-body-tracking)",
        textTransform: head ? "uppercase" : undefined,
        color: "var(--frost-ink)",
        opacity: head ? 0.55 : active ? 1 : 0.55,
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export { StructuredListCell as RowDigestCell };

/* ─── Separator glyph (· at alpha 0.4) — rendered between cells ────────────── */

export function RowDigestSeparator() {
  return (
    <span
      aria-hidden
      style={{
        color: "var(--frost-ink)",
        opacity: 0.4,
        fontFamily: "var(--frost-font-mono)",
        fontSize: "var(--frost-type-mono-body-size)",
        userSelect: "none",
        flexShrink: 0,
      }}
    >
      ·
    </span>
  );
}

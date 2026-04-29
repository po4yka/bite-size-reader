import type { HTMLAttributes, ReactNode } from "react";

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
      className={["rtk-structured-list", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface StructuredListHeadProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function StructuredListHead({
  className,
  children,
  ...rest
}: StructuredListHeadProps) {
  return (
    <div
      role="rowgroup"
      className={["rtk-structured-list__head", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

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
      className={["rtk-structured-list__body", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

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
  children,
  ...rest
}: StructuredListRowProps) {
  void _head;
  void _label;
  return (
    <div
      role="row"
      className={["rtk-structured-list__row", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface StructuredListCellProps extends HTMLAttributes<HTMLDivElement> {
  head?: boolean;
  noWrap?: boolean;
  children?: ReactNode;
}

export function StructuredListCell({
  head = false,
  noWrap: _noWrap,
  className,
  children,
  ...rest
}: StructuredListCellProps) {
  void _noWrap;
  return (
    <div
      role={head ? "columnheader" : "cell"}
      className={[
        "rtk-structured-list__cell",
        head ? "rtk-structured-list__cell--head" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
  type TableHTMLAttributes,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";

export interface TableContainerProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  stickyHeader?: boolean;
  useStaticWidth?: boolean;
  children?: ReactNode;
}

export function TableContainer({
  title,
  description,
  stickyHeader: _stickyHeader,
  useStaticWidth: _useStaticWidth,
  className,
  children,
  ...rest
}: TableContainerProps) {
  void _stickyHeader;
  void _useStaticWidth;
  const cls = ["rtk-table-container", className].filter(Boolean).join(" ");
  return (
    <section className={cls} {...rest}>
      {title || description ? (
        <header className="rtk-table-container__header">
          {title ? <h4 className="rtk-table-container__title">{title}</h4> : null}
          {description ? (
            <p className="rtk-table-container__description">{description}</p>
          ) : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  isSortable?: boolean;
  useZebraStyles?: boolean;
  children?: ReactNode;
}

export const Table = forwardRef<HTMLTableElement, TableProps>(function Table(
  { size: _size, isSortable: _isSortable, useZebraStyles, className, children, ...rest },
  ref,
) {
  void _size;
  void _isSortable;
  const cls = [
    "rtk-table",
    useZebraStyles ? "rtk-table--zebra" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <table ref={ref} className={cls} {...rest}>
      {children}
    </table>
  );
});

export function TableHead({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={["rtk-table__head", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </thead>
  );
}

export function TableBody({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={["rtk-table__body", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </tbody>
  );
}

export interface TableRowProps extends HTMLAttributes<HTMLTableRowElement> {
  isSelected?: boolean;
  isExpanded?: boolean;
  children?: ReactNode;
}

export const TableRow = forwardRef<HTMLTableRowElement, TableRowProps>(
  function TableRow(
    { isSelected, isExpanded, className, children, ...rest },
    ref,
  ) {
    const cls = [
      "rtk-table__row",
      isSelected ? "rtk-table__row--selected" : null,
      isExpanded ? "rtk-table__row--expanded" : null,
      className,
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <tr ref={ref} className={cls} {...rest}>
        {children}
      </tr>
    );
  },
);

export interface TableHeaderProps extends ThHTMLAttributes<HTMLTableCellElement> {
  scope?: "col" | "row";
  isSortable?: boolean;
  isSortHeader?: boolean;
  sortDirection?: "ASC" | "DESC" | "NONE";
  children?: ReactNode;
}

export const TableHeader = forwardRef<HTMLTableCellElement, TableHeaderProps>(
  function TableHeader(
    { scope = "col", isSortable: _isSortable, isSortHeader: _isSortHeader, sortDirection: _sortDirection, className, children, ...rest },
    ref,
  ) {
    void _isSortable;
    void _isSortHeader;
    void _sortDirection;
    return (
      <th
        ref={ref}
        scope={scope}
        className={["rtk-table__header", className].filter(Boolean).join(" ")}
        {...rest}
      >
        {children}
      </th>
    );
  },
);

export interface TableCellProps extends TdHTMLAttributes<HTMLTableCellElement> {
  children?: ReactNode;
}

export const TableCell = forwardRef<HTMLTableCellElement, TableCellProps>(
  function TableCell({ className, children, ...rest }, ref) {
    return (
      <td
        ref={ref}
        className={["rtk-table__cell", className].filter(Boolean).join(" ")}
        {...rest}
      >
        {children}
      </td>
    );
  },
);

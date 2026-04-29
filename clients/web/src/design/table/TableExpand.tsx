import {
  Children,
  cloneElement,
  isValidElement,
  useState,
  type HTMLAttributes,
  type ReactElement,
  type ReactNode,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";

export interface TableExpandHeaderProps extends ThHTMLAttributes<HTMLTableCellElement> {
  ariaLabel?: string;
}

export function TableExpandHeader({
  className,
  ariaLabel,
  ...rest
}: TableExpandHeaderProps) {
  return (
    <th
      scope="col"
      aria-label={ariaLabel}
      className={["rtk-table__expand-header", className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}

export interface TableExpandRowProps extends HTMLAttributes<HTMLTableRowElement> {
  isExpanded?: boolean;
  onExpand?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  ariaLabel?: string;
  expandIconDescription?: string;
  expandHeader?: string;
  children?: ReactNode;
}

export function TableExpandRow({
  isExpanded: controlledExpanded,
  onExpand,
  ariaLabel = "Expand row",
  className,
  children,
  ...rest
}: TableExpandRowProps) {
  const isControlled = controlledExpanded !== undefined;
  const [internal, setInternal] = useState(false);
  const expanded = isControlled ? !!controlledExpanded : internal;

  const handleExpand = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (!isControlled) setInternal((v) => !v);
    onExpand?.(event);
  };

  const cellChildren = Children.toArray(children).filter(isValidElement) as Array<
    ReactElement<HTMLAttributes<HTMLTableCellElement>>
  >;

  return (
    <>
      <tr
        className={[
          "rtk-table__row",
          "rtk-table__row--expandable",
          expanded ? "rtk-table__row--expanded" : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      >
        <td className="rtk-table__expand-cell">
          <button
            type="button"
            aria-label={ariaLabel}
            aria-expanded={expanded}
            onClick={handleExpand}
            className="rtk-table__expand-button"
          >
            {expanded ? "▾" : "▸"}
          </button>
        </td>
        {cellChildren.map((child, idx) =>
          cloneElement(child, { key: child.key ?? idx }),
        )}
      </tr>
    </>
  );
}

export interface TableExpandedRowProps extends TdHTMLAttributes<HTMLTableCellElement> {
  colSpan?: number;
  children?: ReactNode;
}

export function TableExpandedRow({
  colSpan,
  className,
  children,
  ...rest
}: TableExpandedRowProps) {
  return (
    <tr className="rtk-table__row rtk-table__row--expanded-content">
      <td
        colSpan={colSpan}
        className={["rtk-table__expanded-cell", className].filter(Boolean).join(" ")}
        {...rest}
      >
        {children}
      </td>
    </tr>
  );
}

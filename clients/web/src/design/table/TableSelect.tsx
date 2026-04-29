import type { ReactNode } from "react";

export interface TableSelectAllProps {
  id?: string;
  checked?: boolean;
  indeterminate?: boolean;
  onSelect?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  ariaLabel?: string;
  disabled?: boolean;
  name?: string;
  className?: string;
}

export function TableSelectAll({
  id,
  checked = false,
  indeterminate: _indeterminate,
  onSelect,
  ariaLabel = "Select all rows",
  disabled,
  name,
  className,
}: TableSelectAllProps) {
  void _indeterminate;
  return (
    <th
      scope="col"
      className={["rtk-table__select-cell", className].filter(Boolean).join(" ")}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        name={name}
        onChange={onSelect}
        aria-label={ariaLabel}
      />
    </th>
  );
}

export interface TableSelectRowProps {
  id?: string;
  checked?: boolean;
  onSelect?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  ariaLabel?: string;
  disabled?: boolean;
  name?: string;
  className?: string;
  /** Render-prop selection plumbing may pass extra props; ignore unknowns. */
  radio?: boolean;
  children?: ReactNode;
}

export function TableSelectRow({
  id,
  checked = false,
  onSelect,
  ariaLabel = "Select row",
  disabled,
  name,
  className,
  radio,
}: TableSelectRowProps) {
  return (
    <td
      className={["rtk-table__select-cell", className].filter(Boolean).join(" ")}
    >
      <input
        id={id}
        type={radio ? "radio" : "checkbox"}
        checked={checked}
        disabled={disabled}
        name={name}
        onChange={onSelect}
        aria-label={ariaLabel}
      />
    </td>
  );
}

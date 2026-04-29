import {
  forwardRef,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface TableToolbarProps extends HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg";
  children?: ReactNode;
}

export function TableToolbar({
  size: _size,
  className,
  children,
  ...rest
}: TableToolbarProps) {
  void _size;
  return (
    <div
      className={["rtk-table-toolbar", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface TableToolbarContentProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function TableToolbarContent({
  className,
  children,
  ...rest
}: TableToolbarContentProps) {
  return (
    <div
      className={["rtk-table-toolbar__content", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface TableToolbarSearchProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "onChange"> {
  persistent?: boolean;
  expanded?: boolean;
  size?: "sm" | "md" | "lg";
  defaultExpanded?: boolean;
  defaultValue?: string;
  onChange?: (
    event: React.ChangeEvent<HTMLInputElement>,
    state: { value: string },
  ) => void;
  onInput?: (event: React.FormEvent<HTMLInputElement>) => void;
  onClear?: () => void;
}

export const TableToolbarSearch = forwardRef<HTMLInputElement, TableToolbarSearchProps>(
  function TableToolbarSearch(
    {
      persistent: _persistent,
      expanded: _expanded,
      defaultExpanded: _defaultExpanded,
      size: _size,
      onChange,
      onInput,
      onClear,
      className,
      placeholder = "Search",
      id,
      ...rest
    },
    ref,
  ) {
    void _persistent;
    void _expanded;
    void _defaultExpanded;
    void _size;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    return (
      <div
        className={["rtk-table-toolbar-search", className].filter(Boolean).join(" ")}
      >
        <label htmlFor={inputId} className="rtk-visually-hidden">
          Search
        </label>
        <input
          ref={ref}
          id={inputId}
          type="search"
          placeholder={placeholder}
          className="rtk-table-toolbar-search__input"
          onChange={(event) => onChange?.(event, { value: event.currentTarget.value })}
          onInput={onInput}
          {...rest}
        />
        {onClear ? (
          <button
            type="button"
            aria-label="Clear search"
            onClick={onClear}
            className="rtk-table-toolbar-search__clear"
          >
            ×
          </button>
        ) : null}
      </div>
    );
  },
);

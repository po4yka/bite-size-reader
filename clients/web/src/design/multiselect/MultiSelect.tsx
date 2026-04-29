import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface MultiSelectProps<T> {
  id?: string;
  titleText?: ReactNode;
  helperText?: ReactNode;
  label?: ReactNode;
  hideLabel?: boolean;
  items: T[];
  itemToString?: (item: T | null | undefined) => string;
  selectedItems?: T[];
  initialSelectedItems?: T[];
  selectionFeedback?: "top" | "fixed" | "top-after-reopen";
  size?: "sm" | "md" | "lg";
  type?: "default" | "inline";
  disabled?: boolean;
  invalid?: boolean;
  invalidText?: ReactNode;
  light?: boolean;
  open?: boolean;
  onChange?: (state: { selectedItems: T[] | null }) => void;
  onMenuChange?: (open: boolean) => void;
  className?: string;
  placeholder?: ReactNode;
}

export function MultiSelect<T>({
  id,
  titleText,
  label,
  hideLabel = false,
  items,
  itemToString = (item) => (item ? String(item) : ""),
  selectedItems,
  initialSelectedItems = [],
  onChange,
  onMenuChange,
  disabled = false,
  invalid = false,
  invalidText,
  className,
  placeholder,
}: MultiSelectProps<T>) {
  const fallbackId = useId();
  const elementId = id ?? fallbackId;
  const isControlled = selectedItems !== undefined;
  const [internal, setInternal] = useState<T[]>(initialSelectedItems);
  const current = isControlled ? selectedItems! : internal;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
        onMenuChange?.(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onMenuChange]);

  const itemKey = (item: T): string | number => {
    const id = (item as { id?: string | number | null } | null | undefined)?.id;
    return id ?? itemToString(item);
  };

  const selectedSet = useMemo(() => {
    return new Set(current.map(itemKey));
  }, [current, itemToString]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (item: T) => {
    const key = itemKey(item);
    let next: T[];
    if (selectedSet.has(key)) {
      next = current.filter((it) => itemKey(it) !== key);
    } else {
      next = [...current, item];
    }
    if (!isControlled) setInternal(next);
    onChange?.({ selectedItems: next });
  };

  const cls = [
    "rtk-multiselect",
    invalid ? "rtk-multiselect--invalid" : null,
    disabled ? "rtk-multiselect--disabled" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="rtk-form-field" ref={containerRef}>
      {titleText ? (
        <label
          htmlFor={elementId}
          className={
            hideLabel
              ? "rtk-form-field__label rtk-visually-hidden"
              : "rtk-form-field__label"
          }
        >
          {titleText}
        </label>
      ) : null}
      <div className={cls}>
        <button
          id={elementId}
          type="button"
          className="rtk-multiselect__toggle"
          aria-haspopup="listbox"
          aria-expanded={open}
          disabled={disabled}
          onClick={() => {
            const next = !open;
            setOpen(next);
            onMenuChange?.(next);
          }}
        >
          {current.length > 0 ? (
            <span className="rtk-multiselect__count">{current.length}</span>
          ) : null}
          <span className="rtk-multiselect__label">
            {current.length > 0
              ? current.map(itemToString).join(", ")
              : (placeholder ?? label ?? "Choose options")}
          </span>
          <span aria-hidden>▾</span>
        </button>
        {open ? (
          <ul role="listbox" aria-multiselectable className="rtk-multiselect__menu">
            {items.map((item, idx) => {
              const key = itemKey(item);
              const checked = selectedSet.has(key);
              return (
                <li
                  role="option"
                  aria-selected={checked}
                  key={String(key) + ":" + idx}
                  className={[
                    "rtk-multiselect__item",
                    checked ? "rtk-multiselect__item--selected" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => toggle(item)}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    readOnly
                    tabIndex={-1}
                    aria-hidden
                  />
                  <span>{itemToString(item)}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
      {invalid && invalidText ? (
        <div className="rtk-form-field__message rtk-form-field__message--error">
          {invalidText}
        </div>
      ) : null}
    </div>
  );
}

/**
 * `FilterableMultiSelect` adds a typeahead filter on top of `MultiSelect`.
 * The shim implementation reuses MultiSelect with a controlled filter input.
 */
export function FilterableMultiSelect<T>(
  props: MultiSelectProps<T> & {
    onInputValueChange?: (value: string) => void;
    placeholder?: ReactNode;
  },
) {
  const [filter, setFilter] = useState("");
  const { items, itemToString = (it) => (it ? String(it) : ""), ...rest } = props;
  const filtered = useMemo(() => {
    if (!filter.trim()) return items;
    const needle = filter.toLowerCase();
    return items.filter((it) => itemToString(it).toLowerCase().includes(needle));
  }, [items, filter, itemToString]);
  return (
    <div>
      <input
        type="search"
        className="rtk-multiselect__filter"
        placeholder={
          typeof rest.placeholder === "string" ? rest.placeholder : "Filter…"
        }
        value={filter}
        onChange={(event) => {
          setFilter(event.currentTarget.value);
          props.onInputValueChange?.(event.currentTarget.value);
        }}
      />
      <MultiSelect items={filtered} itemToString={itemToString} {...rest} />
    </div>
  );
}

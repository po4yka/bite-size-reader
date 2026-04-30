import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface DropdownProps<T> {
  id?: string;
  titleText?: ReactNode;
  helperText?: ReactNode;
  label?: ReactNode;
  hideLabel?: boolean;
  items: T[];
  itemToString?: (item: T | null | undefined) => string;
  itemToElement?: React.ComponentType<{ item: T }> | null;
  selectedItem?: T | null;
  initialSelectedItem?: T | null;
  size?: "sm" | "md" | "lg";
  type?: "default" | "inline";
  disabled?: boolean;
  invalid?: boolean;
  invalidText?: ReactNode;
  /** Change callback with the selected item. */
  onChange?: (state: { selectedItem: T | null }) => void;
  className?: string;
}

export function Dropdown<T>({
  id,
  titleText,
  label,
  hideLabel = false,
  items,
  itemToString = (item) => (item ? String(item) : ""),
  itemToElement: ItemElement,
  selectedItem,
  initialSelectedItem = null,
  onChange,
  disabled,
  invalid = false,
  invalidText,
  className,
}: DropdownProps<T>) {
  const fallbackId = useId();
  const elementId = id ?? fallbackId;
  const isControlled = selectedItem !== undefined;
  const [internal, setInternal] = useState<T | null>(initialSelectedItem);
  const current = isControlled ? selectedItem : internal;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const choose = (item: T) => {
    if (!isControlled) setInternal(item);
    onChange?.({ selectedItem: item });
    setOpen(false);
  };

  const itemKey = (item: T): string | number => {
    const id = (item as { id?: string | number | null } | null | undefined)?.id;
    return id ?? itemToString(item);
  };

  const cls = [
    "rtk-dropdown",
    invalid ? "rtk-dropdown--invalid" : null,
    disabled ? "rtk-dropdown--disabled" : null,
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
          aria-haspopup="listbox"
          aria-expanded={open}
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          className="rtk-dropdown__toggle"
        >
          <span className="rtk-dropdown__label">
            {current
              ? ItemElement
                ? <ItemElement item={current} />
                : itemToString(current)
              : (label ?? "Choose…")}
          </span>
          <span aria-hidden>▾</span>
        </button>
        {open ? (
          <ul role="listbox" className="rtk-dropdown__menu">
            {items.map((item, idx) => {
              const key = itemKey(item);
              const isCurrent = current != null && itemKey(current) === key;
              return (
                <li
                  role="option"
                  aria-selected={isCurrent || undefined}
                  key={String(key) + ":" + idx}
                  className={[
                    "rtk-dropdown__item",
                    isCurrent ? "rtk-dropdown__item--selected" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => choose(item)}
                >
                  {ItemElement ? <ItemElement item={item} /> : itemToString(item)}
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

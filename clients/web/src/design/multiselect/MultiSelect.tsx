import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/* ─── shared inline styles ─────────────────────────────────────────── */

const monoLabel: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  textTransform: "uppercase",
  letterSpacing: "1px",
  lineHeight: "130%",
};

const triggerStyle = (open: boolean, invalid: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "8px",
  width: "100%",
  background: "var(--frost-page)",
  border: "none",
  borderBottom: invalid
    ? "2px solid var(--frost-spark)"
    : open
      ? "1px solid var(--frost-ink)"
      : "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderRadius: 0,
  padding: "8px 12px",
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  color: "var(--frost-ink)",
  cursor: "pointer",
  textAlign: "left",
});

const menuStyle: React.CSSProperties = {
  position: "absolute",
  top: "100%",
  left: 0,
  right: 0,
  zIndex: 200,
  background: "var(--frost-page)",
  border: "1px solid var(--frost-ink)",
  borderRadius: 0,
  maxHeight: "240px",
  overflowY: "auto",
  listStyle: "none",
  margin: 0,
  padding: 0,
};

/* ─── MultiSelect ───────────────────────────────────────────────────── */

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
    const itemId = (item as { id?: string | number | null } | null | undefined)
      ?.id;
    return itemId ?? itemToString(item);
  };

  const selectedSet = useMemo(
    () => new Set(current.map(itemKey)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [current, itemToString],
  );

  const toggle = (item: T) => {
    const key = itemKey(item);
    const next = selectedSet.has(key)
      ? current.filter((it) => itemKey(it) !== key)
      : [...current, item];
    if (!isControlled) setInternal(next);
    onChange?.({ selectedItems: next });
  };

  return (
    <div
      className={className}
      style={{ fontFamily: "var(--frost-font-mono)", display: "flex", flexDirection: "column", gap: "4px" }}
      ref={containerRef}
    >
      {titleText ? (
        <label
          htmlFor={elementId}
          style={{
            ...monoLabel,
            visibility: hideLabel ? "hidden" : "visible",
          }}
        >
          {titleText}
        </label>
      ) : null}

      <div style={{ position: "relative" }}>
        <button
          id={elementId}
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          disabled={disabled}
          onClick={() => {
            const next = !open;
            setOpen(next);
            onMenuChange?.(next);
          }}
          style={{
            ...triggerStyle(open, invalid),
            opacity: disabled ? 0.4 : 1,
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "6px", overflow: "hidden" }}>
            {current.length > 0 ? (
              /* Chip-style bracketed labels inline */
              current.map((item, i) => (
                <span
                  key={i}
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "11px",
                    fontWeight: 800,
                    textTransform: "uppercase",
                    letterSpacing: "1px",
                    border: "1px solid var(--frost-ink)",
                    padding: "1px 6px",
                    whiteSpace: "nowrap",
                  }}
                >
                  [ {itemToString(item)} ]
                </span>
              ))
            ) : (
              <span style={{ opacity: 0.55 }}>
                {typeof placeholder === "string"
                  ? placeholder
                  : typeof label === "string"
                    ? label
                    : "Choose options"}
              </span>
            )}
          </span>
          <span aria-hidden style={{ flexShrink: 0, opacity: 0.55 }}>
            ▾
          </span>
        </button>

        {open ? (
          <ul role="listbox" aria-multiselectable style={menuStyle}>
            {items.map((item, idx) => {
              const key = itemKey(item);
              const checked = selectedSet.has(key);
              return (
                <li
                  role="option"
                  aria-selected={checked}
                  key={String(key) + ":" + idx}
                  onClick={() => toggle(item)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "8px 12px",
                    cursor: "pointer",
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "13px",
                    fontWeight: checked ? 800 : 500,
                    letterSpacing: "0.4px",
                    borderBottom:
                      "1px solid color-mix(in oklch, var(--frost-ink) 20%, transparent)",
                    background: checked
                      ? "color-mix(in oklch, var(--frost-ink) 8%, var(--frost-page))"
                      : "transparent",
                  }}
                >
                  {/* 12×12 checkbox indicator */}
                  <span
                    style={{
                      width: 12,
                      height: 12,
                      border: "1px solid var(--frost-ink)",
                      borderRadius: 0,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                      fontSize: "9px",
                      fontWeight: 800,
                    }}
                  >
                    {checked ? "✕" : null}
                  </span>
                  <span>{itemToString(item)}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {invalid && invalidText ? (
        <div
          style={{
            fontSize: "11px",
            opacity: 0.85,
            borderLeft: "2px solid var(--frost-spark)",
            paddingLeft: "6px",
          }}
        >
          {invalidText}
        </div>
      ) : null}
    </div>
  );
}

/* ─── FilterableMultiSelect ─────────────────────────────────────────── */

export function FilterableMultiSelect<T>(
  props: MultiSelectProps<T> & {
    onInputValueChange?: (value: string) => void;
    placeholder?: ReactNode;
  },
) {
  const [filter, setFilter] = useState("");
  const {
    items,
    itemToString = (it) => (it ? String(it) : ""),
    onInputValueChange,
    ...rest
  } = props;

  const filtered = useMemo(() => {
    if (!filter.trim()) return items;
    const needle = filter.toLowerCase();
    return items.filter((it) =>
      itemToString(it).toLowerCase().includes(needle),
    );
  }, [items, filter, itemToString]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <input
        type="search"
        placeholder={
          typeof rest.placeholder === "string" ? rest.placeholder : "Filter…"
        }
        value={filter}
        onChange={(event) => {
          setFilter(event.currentTarget.value);
          onInputValueChange?.(event.currentTarget.value);
        }}
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "13px",
          fontWeight: 500,
          letterSpacing: "0.4px",
          border: "none",
          borderBottom:
            "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
          borderRadius: 0,
          padding: "8px 12px",
          background: "transparent",
          color: "var(--frost-ink)",
          outline: "none",
          width: "100%",
          boxSizing: "border-box",
        }}
      />
      <MultiSelect items={filtered} itemToString={itemToString} {...rest} />
    </div>
  );
}

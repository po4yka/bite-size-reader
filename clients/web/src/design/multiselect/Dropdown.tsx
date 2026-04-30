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
    const itemId = (item as { id?: string | number | null } | null | undefined)
      ?.id;
    return itemId ?? itemToString(item);
  };

  return (
    <div
      className={className}
      style={{
        fontFamily: "var(--frost-font-mono)",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
      }}
      ref={containerRef}
    >
      {titleText ? (
        <label
          htmlFor={elementId}
          style={{
            fontSize: "11px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "1px",
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
          onClick={() => setOpen((v) => !v)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            width: "100%",
            background: "var(--frost-page)",
            border: "none",
            borderBottom: invalid
              ? "2px solid var(--frost-spark)"
              : "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
            borderRadius: 0,
            padding: "8px 12px",
            fontFamily: "var(--frost-font-mono)",
            fontSize: "13px",
            fontWeight: 500,
            letterSpacing: "0.4px",
            color: "var(--frost-ink)",
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.4 : 1,
            textAlign: "left",
          }}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {current != null ? (
              ItemElement ? <ItemElement item={current} /> : itemToString(current)
            ) : (
              <span style={{ opacity: 0.55 }}>
                {typeof label === "string" ? label : "Choose…"}
              </span>
            )}
          </span>
          <span aria-hidden style={{ flexShrink: 0, opacity: 0.55 }}>
            ▾
          </span>
        </button>

        {open ? (
          <ul
            role="listbox"
            style={{
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
            }}
          >
            {items.map((item, idx) => {
              const key = itemKey(item);
              const isCurrent = current != null && itemKey(current) === key;
              return (
                <li
                  role="option"
                  aria-selected={isCurrent || undefined}
                  key={String(key) + ":" + idx}
                  onClick={() => choose(item)}
                  style={{
                    padding: "8px 12px",
                    cursor: "pointer",
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "13px",
                    fontWeight: isCurrent ? 800 : 500,
                    letterSpacing: "0.4px",
                    borderBottom:
                      "1px solid color-mix(in oklch, var(--frost-ink) 20%, transparent)",
                    background: isCurrent
                      ? "color-mix(in oklch, var(--frost-ink) 8%, var(--frost-page))"
                      : "transparent",
                    borderLeft: isCurrent
                      ? "2px solid var(--frost-spark)"
                      : "2px solid transparent",
                  }}
                >
                  {ItemElement ? <ItemElement item={item} /> : itemToString(item)}
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

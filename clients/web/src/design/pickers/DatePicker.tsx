import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
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
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const monoInputBase: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  lineHeight: "1.3",
  color: "var(--frost-ink)",
  background: "transparent",
  border: "none",
  borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderRadius: 0,
  padding: "8px 0",
  width: "100%",
  outline: "none",
  cursor: "pointer",
};

const helperStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const errorStyle: React.CSSProperties = {
  ...helperStyle,
  color: "var(--frost-spark)",
};

/* ─── calendar constants ─────────────────────────────────────────── */

const DAY_NAMES = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"] as const;

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function startDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function parseISODate(s: string): Date | null {
  if (!s) return null;
  const d = new Date(s + "T00:00:00");
  return isNaN(d.getTime()) ? null : d;
}

function todayISO(): string {
  return toISODate(new Date());
}

/* ─── Calendar popup ─────────────────────────────────────────────── */

interface CalendarProps {
  value: string;
  minDate?: string;
  maxDate?: string;
  onSelect: (iso: string) => void;
  onClose: () => void;
}

function Calendar({ value, minDate, maxDate, onSelect, onClose }: CalendarProps) {
  const today = todayISO();
  const initial = parseISODate(value) ?? parseISODate(today) ?? new Date();
  const [viewYear, setViewYear] = useState(initial.getFullYear());
  const [viewMonth, setViewMonth] = useState(initial.getMonth());

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  const days = daysInMonth(viewYear, viewMonth);
  const startDay = startDayOfMonth(viewYear, viewMonth);
  const cells: Array<number | null> = [
    ...Array<null>(startDay).fill(null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];
  // Pad to complete grid rows
  while (cells.length % 7 !== 0) cells.push(null);

  const navBtnStyle: React.CSSProperties = {
    fontFamily: "var(--frost-font-mono)",
    fontSize: "11px",
    fontWeight: 800,
    textTransform: "uppercase",
    letterSpacing: "1px",
    border: "1px solid var(--frost-ink)",
    borderRadius: 0,
    background: "var(--frost-page)",
    color: "var(--frost-ink)",
    cursor: "pointer",
    padding: "4px 8px",
    lineHeight: 1,
  };

  return (
    <div
      style={{
        position: "absolute",
        top: "100%",
        left: 0,
        zIndex: 300,
        background: "var(--frost-page)",
        border: "1px solid var(--frost-ink)",
        borderRadius: 0,
        boxShadow: "none",
        padding: "16px",
        minWidth: "240px",
      }}
      role="dialog"
      aria-label="Date picker calendar"
    >
      {/* Month/Year header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
        <button type="button" aria-label="Previous month" onClick={prevMonth} style={navBtnStyle}>
          [ &#8249; ]
        </button>
        <span style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "1px",
        }}>
          {MONTH_NAMES[viewMonth]} {viewYear}
        </span>
        <button type="button" aria-label="Next month" onClick={nextMonth} style={navBtnStyle}>
          [ &#8250; ]
        </button>
      </div>

      {/* Day-name row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 4 }}>
        {DAY_NAMES.map(d => (
          <span key={d} style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "10px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            opacity: 0.4,
            textAlign: "center",
            padding: "2px 0",
          }}>
            {d}
          </span>
        ))}
      </div>

      {/* Day grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
        {cells.map((day, idx) => {
          if (day === null) {
            return <span key={`e-${idx}`} />;
          }
          const iso = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
          const isSelected = iso === value;
          const isToday = iso === today;
          const disabled =
            (minDate != null && iso < minDate) ||
            (maxDate != null && iso > maxDate);

          return (
            <button
              key={iso}
              type="button"
              aria-label={iso}
              aria-pressed={isSelected}
              disabled={disabled}
              onClick={() => { onSelect(iso); onClose(); }}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "12px",
                fontWeight: isSelected ? 800 : 500,
                textAlign: "center",
                padding: "4px 2px",
                border: "none",
                borderLeft: isToday && !isSelected
                  ? "2px solid var(--frost-spark)"
                  : "2px solid transparent",
                borderRadius: 0,
                background: isSelected ? "var(--frost-ink)" : "transparent",
                color: isSelected ? "var(--frost-page)" : "var(--frost-ink)",
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.3 : 1,
              }}
            >
              {day}
            </button>
          );
        })}
      </div>

      {/* Close keyboard hint */}
      <p style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "10px",
        opacity: 0.4,
        textAlign: "right",
        margin: "8px 0 0",
        letterSpacing: "0.5px",
      }}>
        ESC to close
      </p>
    </div>
  );
}

/* ─── DatePicker types ───────────────────────────────────────────── */

export type DatePickerType = "simple" | "single" | "range";

export interface DatePickerProps {
  datePickerType?: DatePickerType;
  dateFormat?: string;
  value?: string | string[];
  onChange?: (dates: Date[]) => void;
  minDate?: string;
  maxDate?: string;
  className?: string;
  children?: ReactNode;
  light?: boolean;
}

/* ─── DatePicker wrapper ─────────────────────────────────────────── */

export function DatePicker({
  datePickerType,
  className,
  children,
  onChange,
  minDate,
  maxDate,
}: DatePickerProps) {
  void datePickerType;
  // For simple type, just delegate change through children
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!onChange) return;
    const raw = event.currentTarget.value;
    if (!raw) { onChange([]); return; }
    const parsed = new Date(raw + "T00:00:00");
    if (isNaN(parsed.getTime())) { onChange([]); return; }
    onChange([parsed]);
  };

  return (
    <div className={className} style={{ position: "relative" }}>
      {/* Pass onChange and min/max down as data so DatePickerInput can pick them up */}
      {children
        ? (() => {
            const items = Array.isArray(children) ? children : [children];
            return items.map((child, idx) => {
              if (!child || typeof child !== "object" || !("props" in child)) return child;
              const c = child as React.ReactElement<DatePickerInputProps>;
              return (
                <DatePickerInput
                  key={idx}
                  {...c.props}
                  onChange={(c.props as DatePickerInputProps).onChange ?? handleChange}
                  min={(c.props as DatePickerInputProps).min ?? minDate}
                  max={(c.props as DatePickerInputProps).max ?? maxDate}
                />
              );
            });
          })()
        : null}
    </div>
  );
}

/* ─── DatePickerInput ────────────────────────────────────────────── */

export interface DatePickerInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  id?: string;
  labelText?: ReactNode;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  size?: "sm" | "md" | "lg";
  hideLabel?: boolean;
  placeholder?: string;
}

export const DatePickerInput = forwardRef<HTMLInputElement, DatePickerInputProps>(
  function DatePickerInput(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      size: _size,
      className,
      placeholder,
      value,
      onChange,
      min,
      max,
      ...rest
    },
    ref,
  ) {
    void _size;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;

    const [open, setOpen] = useState(false);
    const [localValue, setLocalValue] = useState<string>(
      typeof value === "string" ? value : "",
    );
    const containerRef = useRef<HTMLDivElement>(null);

    // sync controlled value
    useEffect(() => {
      if (typeof value === "string") setLocalValue(value);
    }, [value]);

    // close on outside click
    useEffect(() => {
      if (!open) return;
      const handler = (e: MouseEvent) => {
        if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
      };
      document.addEventListener("mousedown", handler);
      return () => document.removeEventListener("mousedown", handler);
    }, [open]);

    // ESC closes
    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    const handleSelect = (iso: string) => {
      setLocalValue(iso);
      if (onChange) {
        // Synthesize a minimal change event
        const synth = {
          currentTarget: { value: iso },
          target: { value: iso },
        } as unknown as React.ChangeEvent<HTMLInputElement>;
        onChange(synth);
      }
    };

    const displayValue = localValue
      ? (() => {
          const d = parseISODate(localValue);
          if (!d) return localValue;
          return `${String(d.getMonth() + 1).padStart(2, "0")} / ${String(d.getDate()).padStart(2, "0")} / ${d.getFullYear()}`;
        })()
      : "";

    const inputStyle: React.CSSProperties = {
      ...monoInputBase,
      ...(invalid ? { borderBottom: "2px solid var(--frost-spark)" } : {}),
    };

    return (
      <div
        ref={containerRef}
        style={{ display: "flex", flexDirection: "column", gap: "4px", position: "relative" }}
        onKeyDown={handleKeyDown}
      >
        {labelText ? (
          <label
            htmlFor={inputId}
            style={
              hideLabel
                ? { ...monoLabel, position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }
                : monoLabel
            }
          >
            {labelText}
          </label>
        ) : null}

        {/* Visible trigger — shows formatted date */}
        <button
          type="button"
          id={inputId}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(o => !o)}
          style={{
            ...inputStyle,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "transparent",
            textAlign: "left",
            cursor: "pointer",
          }}
        >
          <span style={{ opacity: displayValue ? 1 : 0.4 }}>
            {displayValue || (placeholder ?? "MM / DD / YYYY")}
          </span>
          <span aria-hidden style={{ opacity: 0.55, fontSize: "10px" }}>▾</span>
        </button>

        {/* Hidden real input for form submission */}
        <input
          ref={ref}
          type="hidden"
          value={localValue}
          className={className}
          aria-invalid={invalid || undefined}
          {...rest}
          id={undefined}
          onChange={undefined}
          min={min}
          max={max}
        />

        {open ? (
          <Calendar
            value={localValue}
            minDate={typeof min === "string" ? min : undefined}
            maxDate={typeof max === "string" ? max : undefined}
            onSelect={handleSelect}
            onClose={() => setOpen(false)}
          />
        ) : null}

        {invalid && invalidText ? (
          <div style={errorStyle}>{invalidText}</div>
        ) : helperText ? (
          <div style={helperStyle}>{helperText}</div>
        ) : null}
      </div>
    );
  },
);

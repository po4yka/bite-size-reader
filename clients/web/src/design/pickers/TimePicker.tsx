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

const segmentInputStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 800,
  letterSpacing: "0.4px",
  lineHeight: "1.3",
  color: "var(--frost-ink)",
  background: "transparent",
  border: "none",
  borderRadius: 0,
  outline: "none",
  width: "2ch",
  textAlign: "center",
  padding: 0,
  appearance: "textfield" as React.CSSProperties["appearance"],
};

const separatorStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 800,
  color: "color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  userSelect: "none",
  padding: "0 2px",
};

const periodSelectStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  color: "var(--frost-ink)",
  background: "transparent",
  border: "none",
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderRadius: 0,
  outline: "none",
  cursor: "pointer",
  padding: "0 2px",
  appearance: "none" as React.CSSProperties["appearance"],
};

/* ─── Helpers ────────────────────────────────────────────────────── */

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Parse "HH:MM" or "HH:MM AM/PM" into parts. */
function parseTime(value: string): { hh: string; mm: string; period: "AM" | "PM" | null } {
  if (!value) return { hh: "", mm: "", period: null };
  const m = value.match(/^(\d{1,2}):(\d{2})(?:\s*(AM|PM))?$/i);
  if (!m) return { hh: "", mm: "", period: null };
  return {
    hh: pad2(Number(m[1])),
    mm: pad2(Number(m[2])),
    period: m[3] ? (m[3].toUpperCase() as "AM" | "PM") : null,
  };
}

function buildTimeValue(hh: string, mm: string, period: "AM" | "PM" | null): string {
  if (!hh && !mm) return "";
  const h = hh || "00";
  const m = mm || "00";
  return period ? `${h}:${m} ${period}` : `${h}:${m}`;
}

/* ─── TimePicker ──────────────────────────────────────────────────── */

export interface TimePickerProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "type"> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  size?: "sm" | "md" | "lg";
  light?: boolean;
}

export const TimePicker = forwardRef<HTMLInputElement, TimePickerProps>(
  function TimePicker(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      size: _size,
      light: _light,
      className,
      value,
      defaultValue,
      onChange,
      disabled,
      ..._rest
    },
    ref,
  ) {
    void _size;
    void _light;
    void _rest;

    const fallbackId = useId();
    const inputId = id ?? fallbackId;

    const initialStr = typeof value === "string"
      ? value
      : typeof defaultValue === "string"
        ? defaultValue
        : "";

    const initial = parseTime(initialStr);
    const [hh, setHh] = useState(initial.hh);
    const [mm, setMm] = useState(initial.mm);
    // Detect 12h mode from initial value
    const [period, setPeriod] = useState<"AM" | "PM" | null>(initial.period);

    const hhRef = useRef<HTMLInputElement>(null);
    const mmRef = useRef<HTMLInputElement>(null);

    // Sync controlled value
    useEffect(() => {
      if (typeof value === "string") {
        const p = parseTime(value);
        setHh(p.hh);
        setMm(p.mm);
        setPeriod(p.period);
      }
    }, [value]);

    const emit = (nextHh: string, nextMm: string, nextPeriod: "AM" | "PM" | null) => {
      if (!onChange) return;
      const v = buildTimeValue(nextHh, nextMm, nextPeriod);
      const synth = {
        currentTarget: { value: v },
        target: { value: v },
      } as unknown as React.ChangeEvent<HTMLInputElement>;
      onChange(synth);
    };

    const handleHhChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = e.currentTarget.value.replace(/\D/g, "").slice(0, 2);
      const maxH = period ? 12 : 23;
      const n = raw ? String(clamp(Number(raw), 0, maxH)) : "";
      const padded = n.length === 2 ? pad2(Number(n)) : n;
      setHh(padded);
      emit(padded, mm, period);
      // Auto-advance on two-digit entry
      if (raw.length === 2) mmRef.current?.focus();
    };

    const handleHhBlur = () => {
      if (hh && hh.length === 1) {
        const padded = pad2(Number(hh));
        setHh(padded);
        emit(padded, mm, period);
      }
    };

    const handleMmChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = e.currentTarget.value.replace(/\D/g, "").slice(0, 2);
      const n = raw ? String(clamp(Number(raw), 0, 59)) : "";
      const padded = n.length === 2 ? pad2(Number(n)) : n;
      setMm(padded);
      emit(hh, padded, period);
    };

    const handleMmBlur = () => {
      if (mm && mm.length === 1) {
        const padded = pad2(Number(mm));
        setMm(padded);
        emit(hh, padded, period);
      }
    };

    const handlePeriodChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
      const p = e.currentTarget.value as "AM" | "PM";
      setPeriod(p);
      emit(hh, mm, p);
    };

    // Keyboard: arrow up/down increments
    const handleHhKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        const maxH = period ? 12 : 23;
        const current = hh ? Number(hh) : 0;
        const next = e.key === "ArrowUp"
          ? clamp(current + 1, 0, maxH)
          : clamp(current - 1, 0, maxH);
        const padded = pad2(next);
        setHh(padded);
        emit(padded, mm, period);
      }
    };

    const handleMmKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        const current = mm ? Number(mm) : 0;
        const next = e.key === "ArrowUp"
          ? clamp(current + 1, 0, 59)
          : clamp(current - 1, 0, 59);
        const padded = pad2(next);
        setMm(padded);
        emit(hh, padded, period);
      }
      if (e.key === "Backspace" && !mm) {
        hhRef.current?.focus();
      }
    };

    const containerBorderBottom = invalid
      ? "2px solid var(--frost-spark)"
      : "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)";

    const containerStyle: React.CSSProperties = {
      display: "inline-flex",
      alignItems: "center",
      gap: 0,
      borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
      borderBottom: containerBorderBottom,
      borderRadius: 0,
      padding: "8px 0",
      background: "transparent",
      opacity: disabled ? 0.4 : 1,
    };

    return (
      <>
        <style>{`
          .frost-time-hh::-webkit-outer-spin-button,
          .frost-time-hh::-webkit-inner-spin-button,
          .frost-time-mm::-webkit-outer-spin-button,
          .frost-time-mm::-webkit-inner-spin-button {
            -webkit-appearance: none;
            margin: 0;
          }
          .frost-time-hh, .frost-time-mm {
            -moz-appearance: textfield;
          }
          .frost-time-hh:focus, .frost-time-mm:focus {
            background: color-mix(in oklch, var(--frost-ink) 8%, transparent);
            outline: none;
          }
        `}</style>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }} className={className}>
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

          <div style={containerStyle}>
            {/* HH segment */}
            <input
              ref={(node) => {
                (hhRef as React.MutableRefObject<HTMLInputElement | null>).current = node;
                if (typeof ref === "function") ref(node);
                else if (ref) (ref as React.MutableRefObject<HTMLInputElement | null>).current = node;
              }}
              type="text"
              inputMode="numeric"
              className="frost-time-hh"
              placeholder="HH"
              value={hh}
              disabled={disabled}
              aria-label="Hours"
              aria-invalid={invalid || undefined}
              style={segmentInputStyle}
              onChange={handleHhChange}
              onBlur={handleHhBlur}
              onKeyDown={handleHhKey}
              maxLength={2}
              id={inputId}
            />

            <span aria-hidden style={separatorStyle}>:</span>

            {/* MM segment */}
            <input
              ref={mmRef}
              type="text"
              inputMode="numeric"
              className="frost-time-mm"
              placeholder="MM"
              value={mm}
              disabled={disabled}
              aria-label="Minutes"
              style={segmentInputStyle}
              onChange={handleMmChange}
              onBlur={handleMmBlur}
              onKeyDown={handleMmKey}
              maxLength={2}
            />

            {/* AM/PM — only when initial value included period or no period mode */}
            {period !== null ? (
              <>
                <span aria-hidden style={separatorStyle}> </span>
                <select
                  value={period}
                  disabled={disabled}
                  aria-label="Period"
                  style={periodSelectStyle}
                  onChange={handlePeriodChange}
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </>
            ) : null}
          </div>

          {invalid && invalidText ? (
            <div style={errorStyle}>{invalidText}</div>
          ) : helperText ? (
            <div style={helperStyle}>{helperText}</div>
          ) : null}
        </div>
      </>
    );
  },
);

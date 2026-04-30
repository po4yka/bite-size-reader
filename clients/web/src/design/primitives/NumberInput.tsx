import {
  forwardRef,
  type ChangeEvent,
  type ReactNode,
  useId,
  useCallback,
} from "react";

export interface NumberInputProps {
  id?: string;
  label?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  min?: number;
  max?: number;
  step?: number;
  value?: number | string;
  defaultValue?: number | string;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Change callback with the parsed value and optional step direction. */
  onChange?: (
    event: ChangeEvent<HTMLInputElement> | null,
    state: { value: number | string; direction?: "up" | "down" },
  ) => void;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  /** Accepted for icon-only accessibility parity; currently unused. */
  iconDescription?: string;
  hideSteppers?: boolean;
  allowEmpty?: boolean;
}

const numberInputCSS = `
  .frost-number-input-wrap {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .frost-number-input-label {
    font-family: var(--frost-font-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 1px;
    line-height: 1.3;
    text-transform: uppercase;
    color: color-mix(in oklch, var(--frost-ink) 55%, transparent);
    margin: 0;
  }
  .frost-number-input-row {
    display: flex;
    align-items: stretch;
    border-top: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
    border-bottom: 1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent);
  }
  .frost-number-input-row--error {
    border-bottom: 2px solid var(--frost-spark);
  }
  .frost-number-input__input {
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.4px;
    line-height: 1.3;
    color: var(--frost-ink);
    background: transparent;
    border: none;
    outline: none;
    padding: 8px 0;
    flex: 1;
    min-width: 0;
    -moz-appearance: textfield;
  }
  .frost-number-input__input::-webkit-inner-spin-button,
  .frost-number-input__input::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  .frost-number-input__input:focus-visible {
    outline: none;
    border-bottom: 1px solid var(--frost-ink);
  }
  .frost-number-input__steppers {
    display: flex;
    align-items: stretch;
    gap: 0;
    flex-shrink: 0;
  }
  .frost-number-input__stepper {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    align-self: center;
    border: 1px solid var(--frost-ink);
    border-radius: 0;
    background: var(--frost-page);
    color: var(--frost-ink);
    font-family: var(--frost-font-mono);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1px;
    cursor: pointer;
    padding: 0;
    transition: background 0.08s linear, color 0.08s linear;
    margin-left: 4px;
    flex-shrink: 0;
  }
  .frost-number-input__stepper:first-child {
    margin-left: 8px;
  }
  .frost-number-input__stepper:not(:disabled):hover {
    background: var(--frost-ink);
    color: var(--frost-page);
  }
  .frost-number-input__stepper:not(:disabled):active {
    transform: translateY(1px);
  }
  .frost-number-input__stepper:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .frost-number-input__stepper:focus-visible {
    outline: 1px solid var(--frost-ink);
    outline-offset: 2px;
  }
  .frost-number-input__helper {
    font-family: var(--frost-font-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.4px;
    line-height: 1.3;
    color: color-mix(in oklch, var(--frost-ink) 55%, transparent);
    margin: 0;
  }
  .frost-number-input__error {
    font-family: var(--frost-font-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.4px;
    line-height: 1.3;
    color: var(--frost-spark);
    margin: 0;
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-number-input__stepper {
      transition-duration: 0.001s !important;
    }
  }
`;

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  function NumberInput(
    {
      id,
      label,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      min,
      max,
      step = 1,
      value,
      defaultValue,
      disabled = false,
      onChange,
      onBlur,
      className,
      hideSteppers = false,
      allowEmpty = false,
      iconDescription: _iconDescription,
    },
    ref,
  ) {
    void _iconDescription;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;

    const handleChange = useCallback(
      (event: ChangeEvent<HTMLInputElement>) => {
        const raw = event.currentTarget.value;
        const parsed = raw === "" ? (allowEmpty ? "" : 0) : Number(raw);
        onChange?.(event, { value: parsed });
      },
      [onChange, allowEmpty],
    );

    const step1 = (direction: "up" | "down") => {
      const current = typeof value === "number" ? value : Number(value ?? 0);
      const next =
        direction === "up" ? current + step : current - step;
      const clamped =
        max !== undefined && next > max
          ? max
          : min !== undefined && next < min
            ? min
            : next;
      onChange?.(null, { value: clamped, direction });
    };

    return (
      <>
        <style>{numberInputCSS}</style>
        <div className={["frost-number-input-wrap", className].filter(Boolean).join(" ")}>
          {label ? (
            <label
              htmlFor={inputId}
              className="frost-number-input-label"
              style={
                hideLabel
                  ? { position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }
                  : undefined
              }
            >
              {label}
            </label>
          ) : null}
          <div
            className={[
              "frost-number-input-row",
              invalid ? "frost-number-input-row--error" : null,
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <input
              ref={ref}
              id={inputId}
              type="number"
              min={min}
              max={max}
              step={step}
              value={value ?? ""}
              defaultValue={defaultValue}
              disabled={disabled}
              onChange={handleChange}
              onBlur={onBlur}
              aria-invalid={invalid || undefined}
              className="frost-number-input__input"
            />
            {hideSteppers ? null : (
              <div className="frost-number-input__steppers">
                <button
                  type="button"
                  aria-label="Decrement"
                  disabled={disabled}
                  onClick={() => step1("down")}
                  className="frost-number-input__stepper"
                >
                  −
                </button>
                <button
                  type="button"
                  aria-label="Increment"
                  disabled={disabled}
                  onClick={() => step1("up")}
                  className="frost-number-input__stepper"
                >
                  +
                </button>
              </div>
            )}
          </div>
          {invalid && invalidText ? (
            <div className="frost-number-input__error">{invalidText}</div>
          ) : helperText ? (
            <div className="frost-number-input__helper">{helperText}</div>
          ) : null}
        </div>
      </>
    );
  },
);

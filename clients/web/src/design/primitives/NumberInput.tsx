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
  /** Carbon-style: (event, { value, direction }) */
  onChange?: (
    event: ChangeEvent<HTMLInputElement> | null,
    state: { value: number | string; direction?: "up" | "down" },
  ) => void;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  /** Some Carbon callers pass `iconDescription`; accepted but unused */
  iconDescription?: string;
  hideSteppers?: boolean;
  allowEmpty?: boolean;
}

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

    const cls = [
      "rtk-number-input",
      invalid ? "rtk-number-input--invalid" : null,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className="rtk-form-field">
        {label ? (
          <label
            htmlFor={inputId}
            className={
              hideLabel
                ? "rtk-form-field__label rtk-visually-hidden"
                : "rtk-form-field__label"
            }
          >
            {label}
          </label>
        ) : null}
        <div className={cls}>
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
            className="rtk-number-input__input"
          />
          {hideSteppers ? null : (
            <div className="rtk-number-input__steppers">
              <button
                type="button"
                aria-label="Decrement"
                disabled={disabled}
                onClick={() => step1("down")}
                className="rtk-number-input__stepper"
              >
                −
              </button>
              <button
                type="button"
                aria-label="Increment"
                disabled={disabled}
                onClick={() => step1("up")}
                className="rtk-number-input__stepper"
              >
                +
              </button>
            </div>
          )}
        </div>
        {invalid && invalidText ? (
          <div className="rtk-form-field__message rtk-form-field__message--error">
            {invalidText}
          </div>
        ) : helperText ? (
          <div className="rtk-form-field__helper">{helperText}</div>
        ) : null}
      </div>
    );
  },
);

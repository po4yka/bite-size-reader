import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

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
      ...rest
    },
    ref,
  ) {
    void _size;
    void _light;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    return (
      <div className="rtk-form-field">
        {labelText ? (
          <label
            htmlFor={inputId}
            className={
              hideLabel
                ? "rtk-form-field__label rtk-visually-hidden"
                : "rtk-form-field__label"
            }
          >
            {labelText}
          </label>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          type="time"
          className={[
            "rtk-time-picker__input",
            invalid ? "rtk-time-picker__input--invalid" : null,
            className,
          ]
            .filter(Boolean)
            .join(" ")}
          aria-invalid={invalid || undefined}
          {...rest}
        />
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

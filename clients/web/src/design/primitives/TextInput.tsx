import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface TextInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  warn?: boolean;
  warnText?: ReactNode;
  size?: "sm" | "md" | "lg";
  light?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  function TextInput(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      warn = false,
      warnText,
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
    const cls = [
      "rtk-text-input",
      invalid ? "rtk-text-input--invalid" : null,
      warn ? "rtk-text-input--warn" : null,
      className,
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <div className="rtk-form-field">
        {labelText ? (
          <label
            htmlFor={inputId}
            className={
              hideLabel ? "rtk-form-field__label rtk-visually-hidden" : "rtk-form-field__label"
            }
          >
            {labelText}
          </label>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          type={rest.type ?? "text"}
          className={cls}
          aria-invalid={invalid || undefined}
          {...rest}
        />
        {invalid && invalidText ? (
          <div className="rtk-form-field__message rtk-form-field__message--error">
            {invalidText}
          </div>
        ) : warn && warnText ? (
          <div className="rtk-form-field__message rtk-form-field__message--warn">
            {warnText}
          </div>
        ) : helperText ? (
          <div className="rtk-form-field__helper">{helperText}</div>
        ) : null}
      </div>
    );
  },
);

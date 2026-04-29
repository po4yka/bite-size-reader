import {
  forwardRef,
  type TextareaHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  rows?: number;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      rows = 4,
      className,
      ...rest
    },
    ref,
  ) {
    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    const cls = [
      "rtk-text-area",
      invalid ? "rtk-text-area--invalid" : null,
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
        <textarea
          ref={ref}
          id={inputId}
          className={cls}
          rows={rows}
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

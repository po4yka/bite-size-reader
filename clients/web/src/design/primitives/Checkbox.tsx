import {
  forwardRef,
  type ChangeEvent,
  type InputHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  /** Carbon-style: (event, { checked, id }) */
  onChange?: (
    event: ChangeEvent<HTMLInputElement>,
    state: { checked: boolean; id: string },
  ) => void;
  helperText?: ReactNode;
  indeterminate?: boolean;
  invalid?: boolean;
  invalidText?: ReactNode;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    {
      id,
      labelText,
      hideLabel = false,
      onChange,
      helperText,
      indeterminate: _indeterminate,
      invalid = false,
      invalidText,
      className,
      ...rest
    },
    ref,
  ) {
    void _indeterminate;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    return (
      <div className={["rtk-checkbox", className].filter(Boolean).join(" ")}>
        <input
          ref={ref}
          id={inputId}
          type="checkbox"
          className="rtk-checkbox__input"
          onChange={(event) =>
            onChange?.(event, {
              checked: event.currentTarget.checked,
              id: inputId,
            })
          }
          aria-invalid={invalid || undefined}
          {...rest}
        />
        {labelText ? (
          <label
            htmlFor={inputId}
            className={
              hideLabel
                ? "rtk-checkbox__label rtk-visually-hidden"
                : "rtk-checkbox__label"
            }
          >
            {labelText}
          </label>
        ) : null}
        {helperText ? (
          <div className="rtk-form-field__helper">{helperText}</div>
        ) : null}
        {invalid && invalidText ? (
          <div className="rtk-form-field__message rtk-form-field__message--error">
            {invalidText}
          </div>
        ) : null}
      </div>
    );
  },
);

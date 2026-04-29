import {
  forwardRef,
  type SelectHTMLAttributes,
  type OptionHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  inline?: boolean;
  noLabel?: boolean;
  size?: "sm" | "md" | "lg";
  children?: ReactNode;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    id,
    labelText,
    hideLabel = false,
    helperText,
    invalid = false,
    invalidText,
    inline: _inline,
    noLabel = false,
    size: _size,
    className,
    children,
    ...rest
  },
  ref,
) {
  void _inline;
  void _size;
  const fallbackId = useId();
  const selectId = id ?? fallbackId;
  const cls = [
    "rtk-select",
    invalid ? "rtk-select--invalid" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="rtk-form-field">
      {labelText && !noLabel ? (
        <label
          htmlFor={selectId}
          className={
            hideLabel ? "rtk-form-field__label rtk-visually-hidden" : "rtk-form-field__label"
          }
        >
          {labelText}
        </label>
      ) : null}
      <select
        ref={ref}
        id={selectId}
        className={cls}
        aria-invalid={invalid || undefined}
        {...rest}
      >
        {children}
      </select>
      {invalid && invalidText ? (
        <div className="rtk-form-field__message rtk-form-field__message--error">
          {invalidText}
        </div>
      ) : helperText ? (
        <div className="rtk-form-field__helper">{helperText}</div>
      ) : null}
    </div>
  );
});

export interface SelectItemProps extends OptionHTMLAttributes<HTMLOptionElement> {
  value: string | number;
  text: string;
  disabled?: boolean;
  hidden?: boolean;
}

export function SelectItem({ value, text, ...rest }: SelectItemProps) {
  return (
    <option value={value} {...rest}>
      {text}
    </option>
  );
}

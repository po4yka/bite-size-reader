import {
  Children,
  cloneElement,
  forwardRef,
  isValidElement,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  useId,
} from "react";

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

export function DatePicker({
  datePickerType = "single",
  className,
  children,
  onChange,
  minDate,
  maxDate,
}: DatePickerProps) {
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!onChange) return;
    const raw = event.currentTarget.value;
    if (!raw) {
      onChange([]);
      return;
    }
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) {
      onChange([]);
      return;
    }
    onChange([parsed]);
  };

  const items = Children.toArray(children).filter(isValidElement) as Array<
    ReactElement<DatePickerInputProps>
  >;

  return (
    <div
      className={[
        "rtk-date-picker",
        `rtk-date-picker--${datePickerType}`,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {items.map((child, idx) =>
        cloneElement(child, {
          onChange: child.props.onChange ?? handleChange,
          min: child.props.min ?? minDate,
          max: child.props.max ?? maxDate,
          key: idx,
        }),
      )}
    </div>
  );
}

export interface DatePickerInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  id?: string;
  labelText?: ReactNode;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  size?: "sm" | "md" | "lg";
  hideLabel?: boolean;
  /** Native date input placeholder; accepted for API consistency. */
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
      ...rest
    },
    ref,
  ) {
    void _size;
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
          type="date"
          placeholder={placeholder}
          className={[
            "rtk-date-picker__input",
            invalid ? "rtk-date-picker__input--invalid" : null,
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

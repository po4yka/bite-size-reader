import {
  forwardRef,
  type ChangeEvent,
  type InputHTMLAttributes,
  type ReactNode,
  Children,
  cloneElement,
  isValidElement,
  useId,
} from "react";

export interface RadioButtonProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "onChange"> {
  id?: string;
  labelText?: ReactNode;
  value: string | number;
  name?: string;
  checked?: boolean;
  disabled?: boolean;
  onChange?: (
    value: string | number,
    name: string | undefined,
    event: ChangeEvent<HTMLInputElement>,
  ) => void;
}

export const RadioButton = forwardRef<HTMLInputElement, RadioButtonProps>(
  function RadioButton(
    { id, labelText, value, name, checked, disabled, onChange, className, ...rest },
    ref,
  ) {
    const fallbackId = useId();
    const inputId = id ?? fallbackId;
    return (
      <div className={["rtk-radio", className].filter(Boolean).join(" ")}>
        <input
          ref={ref}
          id={inputId}
          type="radio"
          value={value}
          name={name}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange?.(value, name, event)}
          className="rtk-radio__input"
          {...rest}
        />
        {labelText ? (
          <label htmlFor={inputId} className="rtk-radio__label">
            {labelText}
          </label>
        ) : null}
      </div>
    );
  },
);

export interface RadioButtonGroupProps {
  legendText?: ReactNode;
  name?: string;
  valueSelected?: string | number;
  defaultSelected?: string | number;
  onChange?: (
    value: string | number,
    name: string | undefined,
    event: ChangeEvent<HTMLInputElement>,
  ) => void;
  orientation?: "horizontal" | "vertical";
  labelPosition?: "left" | "right";
  disabled?: boolean;
  invalid?: boolean;
  invalidText?: ReactNode;
  helperText?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export function RadioButtonGroup({
  legendText,
  name,
  valueSelected,
  onChange,
  orientation = "horizontal",
  disabled = false,
  invalid = false,
  invalidText,
  helperText,
  className,
  children,
}: RadioButtonGroupProps) {
  const cls = [
    "rtk-radio-group",
    `rtk-radio-group--${orientation}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <fieldset className={cls} disabled={disabled} aria-invalid={invalid || undefined}>
      {legendText ? (
        <legend className="rtk-radio-group__legend">{legendText}</legend>
      ) : null}
      <div className="rtk-radio-group__items">
        {Children.map(children, (child) => {
          if (!isValidElement<RadioButtonProps>(child)) return child;
          return cloneElement(child, {
            name: child.props.name ?? name,
            checked:
              valueSelected !== undefined
                ? child.props.value === valueSelected
                : child.props.checked,
            onChange:
              child.props.onChange ??
              ((value, n, event) => onChange?.(value, n, event)),
          });
        })}
      </div>
      {invalid && invalidText ? (
        <div className="rtk-form-field__message rtk-form-field__message--error">
          {invalidText}
        </div>
      ) : helperText ? (
        <div className="rtk-form-field__helper">{helperText}</div>
      ) : null}
    </fieldset>
  );
}

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
      <div
        className={["frost-radio-label-wrap", className].filter(Boolean).join(" ")}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          fontFamily: "var(--frost-font-mono)",
        }}
      >
        {/* Visually hidden real input */}
        <input
          ref={ref}
          id={inputId}
          type="radio"
          value={value}
          name={name}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange?.(value, name, event)}
          style={{
            position: "absolute",
            width: 1,
            height: 1,
            margin: -1,
            overflow: "hidden",
            clip: "rect(0,0,0,0)",
            whiteSpace: "nowrap",
            border: 0,
          }}
          {...rest}
        />

        {/* Custom 16×16 square frame */}
        <label
          htmlFor={inputId}
          aria-hidden
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 16,
            height: 16,
            border: "1px solid var(--frost-ink)",
            borderRadius: 0,
            background: "var(--frost-page)",
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.4 : 1,
            boxSizing: "border-box",
            flexShrink: 0,
          }}
        >
          {/* 8×8 ink-filled inner square when selected */}
          {checked ? (
            <span
              style={{
                width: 8,
                height: 8,
                background: "var(--frost-ink)",
                borderRadius: 0,
                display: "block",
              }}
            />
          ) : null}
        </label>

        {labelText ? (
          <label
            htmlFor={inputId}
            style={{
              fontSize: "13px",
              fontWeight: 500,
              letterSpacing: "0.4px",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.4 : 1,
            }}
          >
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
  return (
    <fieldset
      className={className}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      style={{
        border: "none",
        padding: 0,
        margin: 0,
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      {legendText ? (
        <legend
          style={{
            fontSize: "11px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "1px",
            marginBottom: "8px",
            opacity: 0.55,
          }}
        >
          {legendText}
        </legend>
      ) : null}
      <div
        style={{
          display: "flex",
          flexDirection: orientation === "vertical" ? "column" : "row",
          gap: "var(--frost-gap-row, 8px)",
          flexWrap: "wrap",
        }}
      >
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
        <div
          style={{
            fontSize: "11px",
            opacity: 0.85,
            borderLeft: "2px solid var(--frost-spark)",
            paddingLeft: "6px",
            marginTop: "4px",
          }}
        >
          {invalidText}
        </div>
      ) : helperText ? (
        <div
          style={{ fontSize: "11px", opacity: 0.55, marginTop: "4px" }}
        >
          {helperText}
        </div>
      ) : null}
    </fieldset>
  );
}

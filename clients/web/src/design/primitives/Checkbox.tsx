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
      checked,
      disabled,
      ...rest
    },
    ref,
  ) {
    void _indeterminate;
    const fallbackId = useId();
    const inputId = id ?? fallbackId;

    return (
      <div
        className={className}
        style={{
          display: "inline-flex",
          flexDirection: "column",
          gap: "4px",
          fontFamily: "var(--frost-font-mono)",
        }}
      >
        <div style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
          {/* Visually hidden real input */}
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            checked={checked}
            disabled={disabled}
            onChange={(event) =>
              onChange?.(event, {
                checked: event.currentTarget.checked,
                id: inputId,
              })
            }
            aria-invalid={invalid || undefined}
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
              border: invalid
                ? "2px solid var(--frost-spark)"
                : "1px solid var(--frost-ink)",
              borderRadius: 0,
              background: "var(--frost-page)",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.4 : 1,
              boxSizing: "border-box",
              flexShrink: 0,
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 800,
              color: "var(--frost-ink)",
              lineHeight: 1,
              userSelect: "none",
            }}
          >
            {checked ? "✕" : null}
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
                visibility: hideLabel ? "hidden" : "visible",
              }}
            >
              {labelText}
            </label>
          ) : null}
        </div>

        {helperText ? (
          <div style={{ fontSize: "11px", opacity: 0.55, letterSpacing: "0.4px" }}>
            {helperText}
          </div>
        ) : null}
        {invalid && invalidText ? (
          <div
            style={{
              fontSize: "11px",
              opacity: 0.85,
              borderLeft: "2px solid var(--frost-spark)",
              paddingLeft: "6px",
            }}
          >
            {invalidText}
          </div>
        ) : null}
      </div>
    );
  },
);

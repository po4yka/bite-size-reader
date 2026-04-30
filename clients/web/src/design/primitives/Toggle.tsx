import {
  forwardRef,
  useState,
  type ChangeEvent,
  type ReactNode,
  useId,
} from "react";

export interface ToggleProps {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  toggled?: boolean;
  defaultToggled?: boolean;
  disabled?: boolean;
  size?: "sm" | "md";
  labelA?: string;
  labelB?: string;
  onToggle?: (
    checked: boolean,
    id: string,
    event: ChangeEvent<HTMLInputElement>,
  ) => void;
  className?: string;
}

export const Toggle = forwardRef<HTMLInputElement, ToggleProps>(function Toggle(
  {
    id,
    labelText,
    hideLabel: _hideLabel,
    toggled,
    defaultToggled = false,
    disabled,
    size: _size,
    labelA = "Off",
    labelB = "On",
    onToggle,
    className,
  },
  ref,
) {
  void _hideLabel;
  void _size;
  const fallbackId = useId();
  const inputId = id ?? fallbackId;

  const isControlled = toggled !== undefined;
  const [internal, setInternal] = useState(defaultToggled);
  const checked = isControlled ? !!toggled : internal;

  return (
    <div
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "10px",
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      {labelText ? (
        <label
          htmlFor={inputId}
          style={{
            fontSize: "11px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "1px",
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.4 : 1,
          }}
        >
          {labelText}
        </label>
      ) : null}

      {/* visually hidden real checkbox drives state */}
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        role="switch"
        checked={checked}
        defaultChecked={isControlled ? undefined : defaultToggled}
        disabled={disabled}
        onChange={(event) => {
          if (!isControlled) setInternal(event.currentTarget.checked);
          onToggle?.(event.currentTarget.checked, inputId, event);
        }}
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
        aria-label={typeof labelText === "string" ? labelText : undefined}
      />

      {/* Square track: 32×16 hairline frame */}
      <label
        htmlFor={inputId}
        aria-hidden
        style={{
          display: "inline-flex",
          alignItems: "center",
          width: 32,
          height: 16,
          border: "1px solid var(--frost-ink)",
          borderRadius: 0,
          background: "var(--frost-page)",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.4 : 1,
          position: "relative",
          boxSizing: "border-box",
          flexShrink: 0,
        }}
      >
        {/* 14×14 ink-filled square thumb */}
        <span
          style={{
            position: "absolute",
            top: 0,
            left: checked ? 16 : 0,
            width: 14,
            height: 14,
            background: "var(--frost-ink)",
            borderRadius: 0,
            transition: "left 0.1s linear",
          }}
        />
      </label>

      {/* State label */}
      <span
        style={{
          fontSize: "11px",
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "1px",
          opacity: disabled ? 0.4 : 0.85,
        }}
      >
        {checked ? labelB : labelA}
      </span>
    </div>
  );
});

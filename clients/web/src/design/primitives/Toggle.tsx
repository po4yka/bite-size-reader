import {
  forwardRef,
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
    defaultToggled,
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
  return (
    <div className={["rtk-toggle", className].filter(Boolean).join(" ")}>
      {labelText ? (
        <label htmlFor={inputId} className="rtk-toggle__label">
          {labelText}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        role="switch"
        checked={toggled}
        defaultChecked={defaultToggled}
        disabled={disabled}
        onChange={(event) =>
          onToggle?.(event.currentTarget.checked, inputId, event)
        }
        className="rtk-toggle__input"
      />
      <span className="rtk-toggle__state">
        {toggled ?? defaultToggled ? labelB : labelA}
      </span>
    </div>
  );
});

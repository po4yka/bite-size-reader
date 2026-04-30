import {
  Children,
  cloneElement,
  isValidElement,
  useState,
  type HTMLAttributes,
  type ReactElement,
  type ReactNode,
} from "react";

export interface ContentSwitcherProps {
  selectedIndex?: number;
  defaultSelectedIndex?: number;
  onChange?: (state: { index: number; name?: string; text?: string }) => void;
  size?: "sm" | "md" | "lg";
  light?: boolean;
  className?: string;
  children?: ReactNode;
}

export function ContentSwitcher({
  selectedIndex,
  defaultSelectedIndex = 0,
  onChange,
  size: _size,
  light: _light,
  className,
  children,
}: ContentSwitcherProps) {
  void _size;
  void _light;
  const isControlled = selectedIndex !== undefined;
  const [internal, setInternal] = useState(defaultSelectedIndex);
  const current = isControlled ? selectedIndex : internal;
  const items = Children.toArray(children).filter(isValidElement) as Array<
    ReactElement<SwitchProps>
  >;
  return (
    <div
      role="tablist"
      className={className}
      style={{
        display: "inline-flex",
        flexDirection: "row",
        gap: "var(--frost-gap-row, 8px)",
        borderBottom:
          "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      {items.map((child, idx) =>
        cloneElement(child, {
          __selected: idx === current,
          __onClick: () => {
            if (!isControlled) setInternal(idx);
            onChange?.({
              index: idx,
              name: child.props.name,
              text: child.props.text,
            });
          },
          key: idx,
        }),
      )}
    </div>
  );
}

export interface SwitchProps extends HTMLAttributes<HTMLButtonElement> {
  name?: string;
  text?: string;
  disabled?: boolean;
  /** internal */
  __selected?: boolean;
  /** internal */
  __onClick?: () => void;
}

export function Switch({
  name: _name,
  text,
  disabled,
  className,
  __selected,
  __onClick,
  children,
  style,
  ...rest
}: SwitchProps) {
  void _name;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={__selected}
      tabIndex={__selected ? 0 : -1}
      disabled={disabled}
      onClick={__onClick}
      className={className}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "11px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "1px",
        lineHeight: "130%",
        background: "transparent",
        border: "none",
        borderLeft: __selected
          ? "2px solid var(--frost-spark)"
          : "2px solid transparent",
        padding: "8px 4px",
        cursor: disabled ? "not-allowed" : "pointer",
        color: "var(--frost-ink)",
        opacity: __selected ? 1 : 0.55,
        transition: "opacity 0.08s linear, border-left-color 0.08s linear",
        ...style,
      }}
      {...rest}
    >
      [ {children ?? text} ]
    </button>
  );
}

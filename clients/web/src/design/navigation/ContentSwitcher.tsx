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
      className={["rtk-content-switcher", className].filter(Boolean).join(" ")}
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
      className={[
        "rtk-content-switcher__item",
        __selected ? "rtk-content-switcher__item--selected" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children ?? text}
    </button>
  );
}

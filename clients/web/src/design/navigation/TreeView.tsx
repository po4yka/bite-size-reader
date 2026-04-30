import {
  Children,
  cloneElement,
  isValidElement,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";

export interface TreeViewProps
  extends Omit<HTMLAttributes<HTMLUListElement>, "onSelect"> {
  label?: ReactNode;
  hideLabel?: boolean;
  selected?: Array<string | number>;
  active?: string | number;
  onSelect?: (
    event: React.MouseEvent<HTMLLIElement>,
    node: { id: string | number },
  ) => void;
  multiselect?: boolean;
  size?: "default" | "compact";
  children?: ReactNode;
}

export function TreeView({
  label,
  hideLabel = true,
  selected: _selected,
  active: _active,
  onSelect: _onSelect,
  multiselect: _multiselect,
  size: _size,
  className,
  style,
  children,
  ...rest
}: TreeViewProps) {
  void _selected;
  void _active;
  void _onSelect;
  void _multiselect;
  void _size;
  return (
    <div
      className={className}
      style={{ fontFamily: "var(--frost-font-mono)", ...style }}
    >
      {label && !hideLabel ? (
        <p
          style={{
            fontSize: "11px",
            fontWeight: 500,
            textTransform: "uppercase",
            letterSpacing: "1px",
            opacity: 0.55,
            marginBottom: "8px",
          }}
        >
          {label}
        </p>
      ) : null}
      <ul role="tree" style={{ listStyle: "none", margin: 0, padding: 0 }} {...rest}>
        {children}
      </ul>
    </div>
  );
}

export interface TreeNodeProps {
  id: string | number;
  label?: ReactNode;
  value?: string | number;
  isExpanded?: boolean;
  defaultIsExpanded?: boolean;
  disabled?: boolean;
  onSelect?: (event: React.MouseEvent<HTMLLIElement>) => void;
  onToggle?: (event: React.MouseEvent, state: { isExpanded: boolean }) => void;
  active?: boolean;
  selected?: boolean;
  className?: string;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  children?: ReactNode;
  depth?: number;
}

export function TreeNode({
  id: _id,
  label,
  isExpanded,
  defaultIsExpanded = false,
  disabled,
  onSelect,
  onToggle,
  active = false,
  selected = false,
  className,
  renderIcon: _renderIcon,
  children,
  depth = 0,
}: TreeNodeProps) {
  void _id;
  void _renderIcon;
  const isControlled = isExpanded !== undefined;
  const [internalOpen, setInternalOpen] = useState(defaultIsExpanded);
  const open = isControlled ? !!isExpanded : internalOpen;
  const hasChildren = Children.count(children) > 0;

  const handleToggle = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (!isControlled) setInternalOpen((v) => !v);
    onToggle?.(event, { isExpanded: !open });
  };

  /* indent guide: 1px ink hairline at parent's glyph column position */
  const indentPx = depth * 24;

  return (
    <li
      role="treeitem"
      aria-selected={selected || undefined}
      aria-expanded={hasChildren ? open : undefined}
      aria-disabled={disabled || undefined}
      className={className}
      onClick={(event) => onSelect?.(event)}
      style={{
        listStyle: "none",
        position: "relative",
        paddingLeft: indentPx,
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      {/* Vertical indent guide line */}
      {depth > 0 ? (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: indentPx - 12,
            top: 0,
            bottom: 0,
            width: 1,
            background:
              "color-mix(in oklch, var(--frost-ink) 40%, transparent)",
            pointerEvents: "none",
          }}
        />
      ) : null}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          padding: "4px 0",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.4 : selected || active ? 1 : 0.85,
        }}
      >
        {hasChildren ? (
          <button
            type="button"
            aria-label={open ? "Collapse" : "Expand"}
            onClick={handleToggle}
            style={{
              background: "transparent",
              border: "none",
              padding: 0,
              cursor: "pointer",
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              color: "var(--frost-ink)",
              opacity: 0.85,
              lineHeight: 1,
              flexShrink: 0,
            }}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span style={{ width: "11px", flexShrink: 0 }} />
        )}
        <span
          style={{
            fontSize: "13px",
            fontWeight: selected || active ? 800 : 500,
            letterSpacing: "0.4px",
            lineHeight: "130%",
          }}
        >
          {label}
        </span>
      </div>

      {hasChildren && open ? (
        <ul role="group" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {Children.map(children, (child) =>
            isValidElement<TreeNodeProps>(child)
              ? cloneElement(child, { depth: depth + 1 })
              : child,
          )}
        </ul>
      ) : null}
    </li>
  );
}

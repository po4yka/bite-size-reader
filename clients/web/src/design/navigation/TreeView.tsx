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
  onSelect?: (event: React.MouseEvent<HTMLLIElement>, node: { id: string | number }) => void;
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
  children,
  ...rest
}: TreeViewProps) {
  void _selected;
  void _active;
  void _onSelect;
  void _multiselect;
  void _size;
  return (
    <div className={["rtk-tree-view", className].filter(Boolean).join(" ")}>
      {label && !hideLabel ? (
        <p className="rtk-tree-view__label">{label}</p>
      ) : null}
      <ul role="tree" {...rest}>
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
  renderIcon: RenderIcon,
  children,
  depth = 0,
}: TreeNodeProps) {
  void _id;
  const isControlled = isExpanded !== undefined;
  const [internalOpen, setInternalOpen] = useState(defaultIsExpanded);
  const open = isControlled ? !!isExpanded : internalOpen;
  const hasChildren = Children.count(children) > 0;
  const handleToggle = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (!isControlled) setInternalOpen((v) => !v);
    onToggle?.(event, { isExpanded: !open });
  };
  return (
    <li
      role="treeitem"
      aria-selected={selected || undefined}
      aria-expanded={hasChildren ? open : undefined}
      aria-disabled={disabled || undefined}
      className={[
        "rtk-tree-node",
        active ? "rtk-tree-node--active" : null,
        selected ? "rtk-tree-node--selected" : null,
        disabled ? "rtk-tree-node--disabled" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={(event) => onSelect?.(event)}
      style={{ paddingLeft: `${depth * 0.75}rem` }}
    >
      <div className="rtk-tree-node__row">
        {hasChildren ? (
          <button
            type="button"
            className="rtk-tree-node__toggle"
            aria-label={open ? "Collapse" : "Expand"}
            onClick={handleToggle}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="rtk-tree-node__toggle-spacer" />
        )}
        {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
        <span className="rtk-tree-node__label">{label}</span>
      </div>
      {hasChildren && open ? (
        <ul role="group" className="rtk-tree-node__group">
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

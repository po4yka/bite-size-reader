import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useMemo,
  useState,
  type HTMLAttributes,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";

/* ─── context ─────────────────────────────────────────────────────── */

interface BracketTabsContextValue {
  selectedIndex: number;
  setSelectedIndex: (i: number) => void;
}
const BracketTabsContext = createContext<BracketTabsContextValue | null>(null);

/* ─── BracketTabs ─────────────────────────────────────────────────── */

export interface BracketTabsProps {
  selectedIndex?: number;
  defaultSelectedIndex?: number;
  onChange?: (state: { selectedIndex: number }) => void;
  className?: string;
  children?: ReactNode;
}

export function BracketTabs({
  selectedIndex,
  defaultSelectedIndex = 0,
  onChange,
  className,
  children,
}: BracketTabsProps) {
  const isControlled = selectedIndex !== undefined;
  const [internal, setInternal] = useState(defaultSelectedIndex);
  const current = isControlled ? selectedIndex : internal;
  const setSelected = useCallback(
    (i: number) => {
      if (!isControlled) setInternal(i);
      onChange?.({ selectedIndex: i });
    },
    [isControlled, onChange],
  );
  const ctx = useMemo(
    () => ({ selectedIndex: current, setSelectedIndex: setSelected }),
    [current, setSelected],
  );
  return (
    <BracketTabsContext.Provider value={ctx}>
      <div
        className={className}
        style={{ fontFamily: "var(--frost-font-mono)" }}
      >
        {children}
      </div>
    </BracketTabsContext.Provider>
  );
}

/* ─── BracketTabList ──────────────────────────────────────────────── */

export interface BracketTabListProps extends HTMLAttributes<HTMLDivElement> {
  "aria-label"?: string;
  contained?: boolean;
  fullWidth?: boolean;
  iconSize?: "default" | "lg";
  children?: ReactNode;
}

export function BracketTabList({
  contained: _contained,
  fullWidth: _fullWidth,
  iconSize: _iconSize,
  children,
  className,
  style,
  ...rest
}: BracketTabListProps) {
  void _contained;
  void _fullWidth;
  void _iconSize;
  const ctx = useContext(BracketTabsContext);
  const items = Children.toArray(children).filter(isValidElement) as Array<
    ReactElement<BracketTabProps>
  >;

  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!ctx) return;
    const count = items.length;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      ctx.setSelectedIndex((ctx.selectedIndex + 1) % count);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      ctx.setSelectedIndex((ctx.selectedIndex - 1 + count) % count);
    } else if (event.key === "Home") {
      event.preventDefault();
      ctx.setSelectedIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      ctx.setSelectedIndex(count - 1);
    }
  };

  return (
    <div
      role="tablist"
      className={className}
      onKeyDown={handleKey}
      style={{
        display: "flex",
        flexDirection: "row",
        gap: "var(--frost-gap-row, 8px)",
        borderBottom:
          "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
        ...style,
      }}
      {...rest}
    >
      {items.map((child, idx) =>
        cloneElement(child, { __index: idx, key: idx }),
      )}
    </div>
  );
}

/* ─── BracketTab ──────────────────────────────────────────────────── */

export interface BracketTabProps extends HTMLAttributes<HTMLButtonElement> {
  disabled?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  children?: ReactNode;
  /** internal */
  __index?: number;
}

export function BracketTab({
  disabled,
  renderIcon: _renderIcon,
  children,
  className,
  __index,
  style,
  ...rest
}: BracketTabProps) {
  void _renderIcon;
  const ctx = useContext(BracketTabsContext);
  const idx = __index ?? 0;
  const selected = ctx?.selectedIndex === idx;

  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      disabled={disabled}
      className={className}
      onClick={(event) => {
        ctx?.setSelectedIndex(idx);
        rest.onClick?.(event);
      }}
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "11px",
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "1px",
        lineHeight: "130%",
        background: "transparent",
        border: "none",
        borderLeft: selected
          ? "2px solid var(--frost-spark)"
          : "2px solid transparent",
        padding: "8px 4px",
        cursor: disabled ? "not-allowed" : "pointer",
        color: "var(--frost-ink)",
        opacity: selected ? 1 : 0.55,
        transition: "opacity 0.08s linear, border-left-color 0.08s linear",
        ...style,
      }}
      {...rest}
    >
      [ {children} ]
    </button>
  );
}

/* ─── BracketTabPanels ────────────────────────────────────────────── */

export interface BracketTabPanelsProps {
  children?: ReactNode;
  className?: string;
}

export function BracketTabPanels({ children, className }: BracketTabPanelsProps) {
  const ctx = useContext(BracketTabsContext);
  const items = Children.toArray(children).filter(isValidElement);
  return (
    <div className={className}>
      {items.map((child, idx) =>
        idx === ctx?.selectedIndex ? <div key={idx}>{child}</div> : null,
      )}
    </div>
  );
}

/* ─── BracketTabPanel ─────────────────────────────────────────────── */

export interface BracketTabPanelProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function BracketTabPanel({
  className,
  children,
  style,
  ...rest
}: BracketTabPanelProps) {
  return (
    <div
      role="tabpanel"
      className={className}
      style={{ padding: "32px 0", ...style }}
      {...rest}
    >
      {children}
    </div>
  );
}

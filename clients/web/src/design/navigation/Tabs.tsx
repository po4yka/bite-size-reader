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

interface TabsContextValue {
  selectedIndex: number;
  setSelectedIndex: (i: number) => void;
}
const TabsContext = createContext<TabsContextValue | null>(null);

export interface TabsProps {
  selectedIndex?: number;
  defaultSelectedIndex?: number;
  onChange?: (state: { selectedIndex: number }) => void;
  className?: string;
  children?: ReactNode;
}

export function Tabs({
  selectedIndex,
  defaultSelectedIndex = 0,
  onChange,
  className,
  children,
}: TabsProps) {
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
    <TabsContext.Provider value={ctx}>
      <div className={["rtk-tabs", className].filter(Boolean).join(" ")}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export interface TabListProps extends HTMLAttributes<HTMLDivElement> {
  "aria-label"?: string;
  contained?: boolean;
  fullWidth?: boolean;
  iconSize?: "default" | "lg";
  children?: ReactNode;
}

export function TabList({
  contained: _contained,
  fullWidth: _fullWidth,
  iconSize: _iconSize,
  children,
  className,
  ...rest
}: TabListProps) {
  void _contained;
  void _fullWidth;
  void _iconSize;
  const ctx = useContext(TabsContext);
  const items = Children.toArray(children).filter(isValidElement) as Array<
    ReactElement<TabProps>
  >;
  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!ctx) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      ctx.setSelectedIndex((ctx.selectedIndex + 1) % items.length);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      ctx.setSelectedIndex(
        (ctx.selectedIndex - 1 + items.length) % items.length,
      );
    }
  };
  return (
    <div
      role="tablist"
      className={["rtk-tab-list", className].filter(Boolean).join(" ")}
      onKeyDown={handleKey}
      {...rest}
    >
      {items.map((child, idx) =>
        cloneElement(child, { __index: idx, key: idx }),
      )}
    </div>
  );
}

export interface TabProps extends HTMLAttributes<HTMLButtonElement> {
  disabled?: boolean;
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  children?: ReactNode;
  /** internal */
  __index?: number;
}

export function Tab({
  disabled,
  renderIcon: RenderIcon,
  children,
  className,
  __index,
  ...rest
}: TabProps) {
  const ctx = useContext(TabsContext);
  const idx = __index ?? 0;
  const selected = ctx?.selectedIndex === idx;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      disabled={disabled}
      className={[
        "rtk-tab",
        selected ? "rtk-tab--selected" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={(event) => {
        ctx?.setSelectedIndex(idx);
        rest.onClick?.(event);
      }}
      {...rest}
    >
      {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
      <span>{children}</span>
    </button>
  );
}

export interface TabPanelsProps {
  children?: ReactNode;
  className?: string;
}

export function TabPanels({ children, className }: TabPanelsProps) {
  const ctx = useContext(TabsContext);
  const items = Children.toArray(children).filter(isValidElement);
  return (
    <div className={["rtk-tab-panels", className].filter(Boolean).join(" ")}>
      {items.map((child, idx) =>
        idx === ctx?.selectedIndex ? <div key={idx}>{child}</div> : null,
      )}
    </div>
  );
}

export interface TabPanelProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function TabPanel({ className, children, ...rest }: TabPanelProps) {
  return (
    <div
      role="tabpanel"
      className={["rtk-tab-panel", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}

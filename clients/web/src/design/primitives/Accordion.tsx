import {
  useState,
  type ReactNode,
  type HTMLAttributes,
} from "react";

export interface AccordionProps extends HTMLAttributes<HTMLDivElement> {
  align?: "start" | "end";
  size?: "sm" | "md" | "lg";
  isFlush?: boolean;
  children?: ReactNode;
}

export function Accordion({
  align: _align,
  size: _size,
  isFlush: _isFlush,
  className,
  style,
  children,
  ...rest
}: AccordionProps) {
  void _align;
  void _size;
  void _isFlush;
  return (
    <div
      className={className}
      style={{
        fontFamily: "var(--frost-font-mono)",
        width: "100%",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface AccordionItemProps {
  title?: ReactNode;
  open?: boolean;
  disabled?: boolean;
  className?: string;
  children?: ReactNode;
  onHeadingClick?: (state: { isOpen: boolean }) => void;
}

export function AccordionItem({
  title,
  open,
  disabled,
  className,
  children,
  onHeadingClick,
}: AccordionItemProps) {
  const isControlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const isOpen = isControlled ? !!open : internalOpen;

  return (
    <div
      className={className}
      style={{
        borderBottom: "1px solid var(--frost-ink)",
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      <button
        type="button"
        disabled={disabled}
        aria-expanded={isOpen}
        onClick={() => {
          if (!isControlled) setInternalOpen((v) => !v);
          onHeadingClick?.({ isOpen: !isOpen });
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          width: "100%",
          background: "transparent",
          border: "none",
          padding: "12px 0",
          cursor: disabled ? "not-allowed" : "pointer",
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "1px",
          lineHeight: "130%",
          color: "var(--frost-ink)",
          opacity: disabled ? 0.4 : 0.85,
          textAlign: "left",
        }}
      >
        <span aria-hidden style={{ flexShrink: 0, opacity: 0.85 }}>
          {isOpen ? "▾" : "▸"}
        </span>
        <span>{title}</span>
      </button>
      {isOpen ? (
        <div
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "13px",
            fontWeight: 500,
            lineHeight: "130%",
            letterSpacing: "0.4px",
            padding: "16px 0",
            color: "var(--frost-ink)",
          }}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

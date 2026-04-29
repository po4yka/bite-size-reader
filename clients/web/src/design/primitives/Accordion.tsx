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
  children,
  ...rest
}: AccordionProps) {
  void _align;
  void _size;
  void _isFlush;
  const cls = ["rtk-accordion", className].filter(Boolean).join(" ");
  return (
    <div className={cls} {...rest}>
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
  const cls = [
    "rtk-accordion-item",
    isOpen ? "rtk-accordion-item--open" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      <button
        type="button"
        className="rtk-accordion-item__heading"
        disabled={disabled}
        aria-expanded={isOpen}
        onClick={() => {
          if (!isControlled) setInternalOpen((v) => !v);
          onHeadingClick?.({ isOpen: !isOpen });
        }}
      >
        <span className="rtk-accordion-item__chevron" aria-hidden>
          {isOpen ? "▾" : "▸"}
        </span>
        <span className="rtk-accordion-item__title">{title}</span>
      </button>
      {isOpen ? (
        <div className="rtk-accordion-item__panel">{children}</div>
      ) : null}
    </div>
  );
}

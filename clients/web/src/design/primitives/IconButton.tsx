import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  align?: "top" | "bottom" | "left" | "right";
  kind?: "primary" | "secondary" | "tertiary" | "ghost";
  size?: "sm" | "md" | "lg";
  children?: ReactNode;
}

const iconButtonCSS = `
  .frost-icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: 1px solid var(--frost-ink);
    border-radius: 0;
    background: var(--frost-page);
    color: var(--frost-ink);
    cursor: pointer;
    padding: 0;
    transition: background 0.08s linear, color 0.08s linear;
    flex-shrink: 0;
  }
  .frost-icon-btn:not(:disabled):hover {
    background: var(--frost-ink);
    color: var(--frost-page);
  }
  .frost-icon-btn:not(:disabled):active {
    transform: translateY(1px);
  }
  .frost-icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .frost-icon-btn:focus-visible {
    outline: 1px solid var(--frost-ink);
    outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-icon-btn {
      transition-duration: 0.001s !important;
    }
  }
`;

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { label, align: _align, kind: _kind, size: _size, className, children, ...rest },
    ref,
  ) {
    void _align;
    void _kind;
    void _size;

    return (
      <>
        <style>{iconButtonCSS}</style>
        <button
          ref={ref}
          type="button"
          className={["frost-icon-btn", className].filter(Boolean).join(" ")}
          aria-label={label}
          title={label}
          {...rest}
        >
          {children}
        </button>
      </>
    );
  },
);

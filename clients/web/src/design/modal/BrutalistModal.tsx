import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { BracketButton } from "../primitives/BracketButton";

/* ─── shared inline styles ─────────────────────────────────────────── */

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "color-mix(in oklch, var(--frost-page) 85%, transparent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
  animation: "frost-modal-in 0.12s linear",
};

const mobileModalCSS = `
@container main (max-width: 768px) {
  .brutalist-modal__frame {
    max-width: none;
    max-height: none;
    width: 100vw;
    height: 100vh;
    border: none;
    border-radius: 0;
  }
  .brutalist-modal__backdrop {
    align-items: flex-start;
    justify-content: flex-start;
  }
}
`;

const frameStyle = (size: "sm" | "md"): React.CSSProperties => ({
  position: "relative",
  background: "var(--frost-page)",
  border: "1px solid var(--frost-ink)",
  borderRadius: 0,
  boxShadow: "none",
  width: "100%",
  maxWidth: size === "sm" ? "var(--frost-strip-3)" : "var(--frost-strip-5)",
  maxHeight: "90vh",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
});

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "16px 32px",
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  flexShrink: 0,
};

const headingStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  lineHeight: "130%",
  margin: 0,
};

const closeButtonStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  border: "1px solid var(--frost-ink)",
  borderRadius: 0,
  background: "var(--frost-page)",
  color: "var(--frost-ink)",
  cursor: "pointer",
  padding: "4px 8px",
  lineHeight: 1,
  flexShrink: 0,
};

const bodyStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  lineHeight: "130%",
  padding: "32px",
  overflowY: "auto",
  flex: 1,
};

const footerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "row",
  justifyContent: "flex-end",
  gap: "16px",
  padding: "16px 32px",
  borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  flexShrink: 0,
};

const keyframes = `
@keyframes frost-modal-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  @keyframes frost-modal-in {
    from { opacity: 1; }
    to   { opacity: 1; }
  }
}
`;

/* ─── focus trap helper ─────────────────────────────────────────────── */

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function trapFocus(container: HTMLElement, event: KeyboardEvent) {
  const els = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (!els.length) return;
  const first = els[0];
  const last = els[els.length - 1];
  if (event.key === "Tab") {
    if (event.shiftKey) {
      if (document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }
}

/* ─── BrutalistModal (replaces Modal + ComposedModal) ───────────────── */

/**
 * BrutalistModal — Frost-style dialog. Replaces both the legacy `Modal` and
 * `ComposedModal` primitives.
 *
 * **Two usage patterns:**
 *
 * 1. **Simple (Modal-equivalent):** Pass `modalHeading` (and optionally
 *    `modalLabel`) together with `primaryButtonText` / `secondaryButtonText`
 *    and the `onRequestClose` / `onRequestSubmit` callbacks. The component
 *    renders the header, body, and footer chrome automatically.
 *
 * 2. **Composed (ComposedModal-equivalent):** Omit `modalHeading` and
 *    `passiveModal`; supply `<BrutalistModalHeader>`, `<BrutalistModalBody>`,
 *    and `<BrutalistModalFooter>` as direct children.
 *
 * **passiveModal behaviour:**
 * When `passiveModal=true` the modal renders the header close-button as
 * normal (the user must be able to dismiss the dialog), renders `children`
 * directly in the body, and suppresses the footer action buttons entirely.
 * No secondary close-button or primary submit button is auto-generated.
 * Call sites that need a footer should supply `<BrutalistModalFooter>` as a
 * child instead of relying on the auto-generated one.
 */
export interface BrutalistModalProps {
  open?: boolean;
  /** "sm" → strip-3 (528px confirm), "md" → strip-5 (880px content) */
  size?: "sm" | "md";
  danger?: boolean;
  /** Used by the simple (Modal-equivalent) variant for a heading. */
  modalHeading?: ReactNode;
  modalLabel?: ReactNode;
  primaryButtonText?: ReactNode;
  secondaryButtonText?: ReactNode;
  primaryButtonDisabled?: boolean;
  passiveModal?: boolean;
  preventCloseOnClickOutside?: boolean;
  onRequestClose?: () => void;
  onRequestSubmit?: () => void;
  onSecondarySubmit?: () => void;
  /** Alias used by ComposedModal callers. */
  onClose?: () => void;
  className?: string;
  children?: ReactNode;
}

export function BrutalistModal({
  open = false,
  size = "md",
  danger = false,
  modalHeading,
  modalLabel,
  primaryButtonText = "Submit",
  secondaryButtonText = "Cancel",
  primaryButtonDisabled = false,
  passiveModal = false,
  preventCloseOnClickOutside = false,
  onRequestClose,
  onRequestSubmit,
  onSecondarySubmit,
  onClose,
  className,
  children,
}: BrutalistModalProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const requestClose = onRequestClose ?? onClose;

  /* focus first element on open */
  useEffect(() => {
    if (!open) return;
    const frame = frameRef.current;
    if (!frame) return;
    const firstFocusable = frame.querySelector<HTMLElement>(FOCUSABLE);
    firstFocusable?.focus();
  }, [open]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (preventCloseOnClickOutside) return;
      if (e.target === e.currentTarget) requestClose?.();
    },
    [preventCloseOnClickOutside, requestClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault();
        requestClose?.();
        return;
      }
      if (frameRef.current) trapFocus(frameRef.current, e);
    },
    [requestClose],
  );

  if (!open) return null;

  /* detect if children already include sub-components (ComposedModal style) */
  const isComposed = modalHeading === undefined && !passiveModal;

  const dangerStyle: React.CSSProperties = danger
    ? { borderLeft: "2px solid var(--frost-spark)" }
    : {};

  return (
    <>
      <style>{keyframes}</style>
      <style>{mobileModalCSS}</style>
      <div
        className="brutalist-modal__backdrop"
        style={backdropStyle}
        onClick={handleBackdropClick}
        onKeyDown={handleKeyDown}
        role="presentation"
      >
        <div
          ref={frameRef}
          role="dialog"
          aria-modal
          aria-label={typeof modalHeading === "string" ? modalHeading : undefined}
          className={["brutalist-modal__frame", className].filter(Boolean).join(" ")}
          style={{ ...frameStyle(size), ...dangerStyle }}
        >
          {/* Simple modal header */}
          {modalHeading !== undefined || modalLabel !== undefined ? (
            <header style={headerStyle}>
              <div>
                {modalLabel ? (
                  <p
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "11px",
                      fontWeight: 500,
                      textTransform: "uppercase",
                      letterSpacing: "1px",
                      opacity: 0.55,
                      margin: "0 0 4px",
                    }}
                  >
                    {modalLabel}
                  </p>
                ) : null}
                {modalHeading ? (
                  <h2 style={headingStyle}>{modalHeading}</h2>
                ) : null}
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={requestClose}
                style={closeButtonStyle}
              >
                [ &times; ]
              </button>
            </header>
          ) : null}

          {/* Composed style — children include ModalHeader / ModalBody / ModalFooter */}
          {isComposed ? (
            children
          ) : (
            <>
              <div style={bodyStyle}>{children}</div>
              {passiveModal ? null : (
                <footer style={footerStyle}>
                  {secondaryButtonText ? (
                    <button
                      type="button"
                      onClick={onSecondarySubmit ?? requestClose}
                      style={closeButtonStyle}
                    >
                      [ {secondaryButtonText} ]
                    </button>
                  ) : null}
                  {primaryButtonText ? (
                    <button
                      type="button"
                      disabled={primaryButtonDisabled}
                      onClick={onRequestSubmit}
                      style={{
                        ...closeButtonStyle,
                        ...(danger
                          ? { borderLeft: "2px solid var(--frost-spark)" }
                          : {}),
                        ...(primaryButtonDisabled
                          ? { opacity: 0.4, cursor: "not-allowed" }
                          : {}),
                      }}
                    >
                      [ {primaryButtonText} ]
                    </button>
                  ) : null}
                </footer>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

/* ─── Sub-components for ComposedModal-style usage ─────────────────── */

export interface ModalHeaderProps {
  title?: ReactNode;
  label?: ReactNode;
  iconDescription?: string;
  closeModal?: () => void;
  buttonOnClick?: () => void;
  className?: string;
  children?: ReactNode;
}

export function ModalHeader({
  title,
  label,
  closeModal,
  children,
}: ModalHeaderProps) {
  return (
    <header style={headerStyle}>
      <div>
        {label ? (
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "1px",
              opacity: 0.55,
              margin: "0 0 4px",
            }}
          >
            {label}
          </p>
        ) : null}
        {title ? <h2 style={headingStyle}>{title}</h2> : null}
        {children}
      </div>
      {closeModal ? (
        <button
          type="button"
          aria-label="Close"
          onClick={closeModal}
          style={closeButtonStyle}
        >
          [ &times; ]
        </button>
      ) : null}
    </header>
  );
}

export interface ModalBodyProps {
  hasScrollingContent?: boolean;
  hasForm?: boolean;
  className?: string;
  children?: ReactNode;
}

export function ModalBody({ children }: ModalBodyProps) {
  return <div style={bodyStyle}>{children}</div>;
}

export interface ModalFooterProps {
  primaryButtonText?: ReactNode;
  secondaryButtonText?: ReactNode;
  primaryButtonDisabled?: boolean;
  danger?: boolean;
  onRequestClose?: () => void;
  onRequestSubmit?: () => void;
  className?: string;
  children?: ReactNode;
}

export function ModalFooter({
  primaryButtonText,
  secondaryButtonText,
  primaryButtonDisabled = false,
  danger = false,
  onRequestClose,
  onRequestSubmit,
  children,
}: ModalFooterProps) {
  return (
    <footer style={footerStyle}>
      {children}
      {onRequestClose != null || secondaryButtonText != null ? (
        <BracketButton
          kind="secondary"
          size="sm"
          onClick={onRequestClose}
        >
          {secondaryButtonText ?? "Cancel"}
        </BracketButton>
      ) : null}
      {primaryButtonText != null ? (
        <BracketButton
          kind={danger ? "danger--primary" : "primary"}
          size="sm"
          disabled={primaryButtonDisabled}
          danger={danger}
          onClick={onRequestSubmit}
        >
          {primaryButtonText}
        </BracketButton>
      ) : null}
    </footer>
  );
}

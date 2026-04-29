import { useEffect, useRef, type ReactNode } from "react";

export interface ModalProps {
  open?: boolean;
  modalHeading?: ReactNode;
  modalLabel?: ReactNode;
  primaryButtonText?: ReactNode;
  secondaryButtonText?: ReactNode;
  primaryButtonDisabled?: boolean;
  size?: "xs" | "sm" | "md" | "lg";
  danger?: boolean;
  passiveModal?: boolean;
  preventCloseOnClickOutside?: boolean;
  selectorPrimaryFocus?: string;
  hasScrollingContent?: boolean;
  onRequestClose?: () => void;
  onRequestSubmit?: () => void;
  onSecondarySubmit?: () => void;
  className?: string;
  children?: ReactNode;
}

export function Modal({
  open = false,
  modalHeading,
  modalLabel,
  primaryButtonText = "Submit",
  secondaryButtonText = "Cancel",
  primaryButtonDisabled = false,
  danger = false,
  passiveModal = false,
  preventCloseOnClickOutside = false,
  onRequestClose,
  onRequestSubmit,
  onSecondarySubmit,
  className,
  children,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      try {
        dialog.showModal();
      } catch {
        /* showModal throws if jsdom; fall back to attribute */
        dialog.setAttribute("open", "");
      }
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  if (!open) return null;
  const cls = [
    "rtk-modal",
    danger ? "rtk-modal--danger" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <dialog
      ref={dialogRef}
      className={cls}
      onClose={onRequestClose}
      onClick={(event) => {
        if (preventCloseOnClickOutside) return;
        if (event.target === dialogRef.current) {
          onRequestClose?.();
        }
      }}
    >
      <div className="rtk-modal__container">
        <header className="rtk-modal__header">
          {modalLabel ? (
            <p className="rtk-modal__label">{modalLabel}</p>
          ) : null}
          {modalHeading ? (
            <h2 className="rtk-modal__heading">{modalHeading}</h2>
          ) : null}
          <button
            type="button"
            aria-label="Close"
            onClick={onRequestClose}
            className="rtk-modal__close"
          >
            ×
          </button>
        </header>
        <div className="rtk-modal__body">{children}</div>
        {passiveModal ? null : (
          <footer className="rtk-modal__footer">
            {secondaryButtonText ? (
              <button
                type="button"
                className="rtk-button rtk-button--secondary rtk-button--md"
                onClick={onSecondarySubmit ?? onRequestClose}
              >
                {secondaryButtonText}
              </button>
            ) : null}
            {primaryButtonText ? (
              <button
                type="button"
                className={[
                  "rtk-button",
                  danger ? "rtk-button--danger" : "rtk-button--primary",
                  "rtk-button--md",
                ].join(" ")}
                disabled={primaryButtonDisabled}
                onClick={onRequestSubmit}
              >
                {primaryButtonText}
              </button>
            ) : null}
          </footer>
        )}
      </div>
    </dialog>
  );
}

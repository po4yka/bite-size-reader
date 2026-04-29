import { useEffect, useRef, type ReactNode } from "react";

export interface ComposedModalProps {
  open?: boolean;
  size?: "xs" | "sm" | "md" | "lg";
  danger?: boolean;
  preventCloseOnClickOutside?: boolean;
  onClose?: () => void;
  className?: string;
  children?: ReactNode;
}

export function ComposedModal({
  open = false,
  danger = false,
  preventCloseOnClickOutside = false,
  onClose,
  className,
  children,
}: ComposedModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      try {
        dialog.showModal();
      } catch {
        dialog.setAttribute("open", "");
      }
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  if (!open) return null;
  return (
    <dialog
      ref={dialogRef}
      className={[
        "rtk-modal",
        danger ? "rtk-modal--danger" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClose={onClose}
      onClick={(event) => {
        if (preventCloseOnClickOutside) return;
        if (event.target === dialogRef.current) {
          onClose?.();
        }
      }}
    >
      <div className="rtk-modal__container">{children}</div>
    </dialog>
  );
}

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
  className,
  children,
}: ModalHeaderProps) {
  return (
    <header className={["rtk-modal__header", className].filter(Boolean).join(" ")}>
      {label ? <p className="rtk-modal__label">{label}</p> : null}
      {title ? <h2 className="rtk-modal__heading">{title}</h2> : null}
      {children}
      {closeModal ? (
        <button
          type="button"
          aria-label="Close"
          onClick={closeModal}
          className="rtk-modal__close"
        >
          ×
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

export function ModalBody({
  hasScrollingContent: _hasScrollingContent,
  hasForm: _hasForm,
  className,
  children,
}: ModalBodyProps) {
  void _hasScrollingContent;
  void _hasForm;
  return (
    <div className={["rtk-modal__body", className].filter(Boolean).join(" ")}>
      {children}
    </div>
  );
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
  className,
  children,
}: ModalFooterProps) {
  return (
    <footer className={["rtk-modal__footer", className].filter(Boolean).join(" ")}>
      {children}
    </footer>
  );
}

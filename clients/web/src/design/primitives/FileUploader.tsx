import {
  type ChangeEvent,
  type ReactNode,
  useId,
  useRef,
} from "react";

export interface FileUploaderProps {
  labelTitle?: ReactNode;
  labelDescription?: ReactNode;
  buttonLabel?: ReactNode;
  buttonKind?: "primary" | "secondary" | "tertiary" | "ghost" | "danger" | "danger--ghost" | "danger--tertiary";
  filenameStatus?: "edit" | "complete" | "uploading";
  accept?: string[] | string;
  multiple?: boolean;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  iconDescription?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  /** Called when the user clears the selected file. */
  onDelete?: () => void;
  className?: string;
  id?: string;
}

export function FileUploader({
  labelTitle,
  labelDescription,
  buttonLabel = "Choose file",
  accept,
  multiple = false,
  disabled = false,
  onChange,
  onDelete,
  className,
  id,
}: FileUploaderProps) {
  void onDelete;
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const inputRef = useRef<HTMLInputElement | null>(null);
  const acceptStr = Array.isArray(accept) ? accept.join(",") : accept;
  return (
    <div className={["rtk-file-uploader", className].filter(Boolean).join(" ")}>
      {labelTitle ? (
        <p className="rtk-file-uploader__title">{labelTitle}</p>
      ) : null}
      {labelDescription ? (
        <p className="rtk-file-uploader__description">{labelDescription}</p>
      ) : null}
      <button
        type="button"
        className="rtk-file-uploader__button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {buttonLabel}
      </button>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={acceptStr}
        multiple={multiple}
        disabled={disabled}
        onChange={onChange}
        className="rtk-visually-hidden"
      />
    </div>
  );
}

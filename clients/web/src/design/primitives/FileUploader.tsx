import {
  type ChangeEvent,
  type ReactNode,
  useId,
  useRef,
  useState,
} from "react";

export interface FileUploaderProps {
  labelTitle?: ReactNode;
  labelDescription?: ReactNode;
  buttonLabel?: ReactNode;
  buttonKind?:
    | "primary"
    | "secondary"
    | "tertiary"
    | "ghost"
    | "danger"
    | "danger--ghost"
    | "danger--tertiary";
  filenameStatus?: "edit" | "complete" | "uploading";
  accept?: string[] | string;
  multiple?: boolean;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  iconDescription?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  onDelete?: () => void;
  className?: string;
  id?: string;
}

const monoLabel: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  lineHeight: "130%",
};

export function FileUploader({
  labelTitle,
  labelDescription,
  accept,
  multiple = false,
  disabled = false,
  onChange,
  onDelete,
  className,
  id,
}: FileUploaderProps) {
  const fallbackId = useId();
  const inputId = id ?? fallbackId;
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const acceptStr = Array.isArray(accept) ? accept.join(",") : accept;

  const handleFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const arr = Array.from(incoming);
    setFiles((prev) => (multiple ? [...prev, ...arr] : arr));
  };

  return (
    <div
      className={className}
      style={{ fontFamily: "var(--frost-font-mono)", display: "flex", flexDirection: "column", gap: "8px" }}
    >
      {labelTitle ? (
        <p style={{ ...monoLabel, margin: 0 }}>{labelTitle}</p>
      ) : null}
      {labelDescription ? (
        <p style={{ fontSize: "13px", fontWeight: 500, letterSpacing: "0.4px", margin: 0, opacity: 0.55 }}>
          {labelDescription}
        </p>
      ) : null}

      {/* Drop zone */}
      <div
        role="button"
        aria-label="Drop file or click to upload"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (!disabled) handleFiles(e.dataTransfer.files);
        }}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: dragOver
            ? "2px solid var(--frost-ink)"
            : "1px solid var(--frost-ink)",
          borderRadius: 0,
          padding: "24px 32px",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.4 : 1,
          ...monoLabel,
        }}
      >
        [ DROP FILE OR CLICK ]
      </div>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={acceptStr}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => {
          handleFiles(e.currentTarget.files);
          onChange?.(e);
        }}
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
      />

      {/* File list */}
      {files.length > 0 ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "4px" }}>
          {files.map((file, idx) => (
            <li
              key={`${file.name}:${idx}`}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "8px",
                padding: "6px 12px",
                border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
                fontFamily: "var(--frost-font-mono)",
                fontSize: "13px",
                fontWeight: 500,
                letterSpacing: "0.4px",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {file.name}
              </span>
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                onClick={() => {
                  setFiles((prev) => prev.filter((_, i) => i !== idx));
                  onDelete?.();
                }}
                style={{
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
                  padding: "2px 6px",
                  lineHeight: 1,
                  flexShrink: 0,
                }}
              >
                [ &times; ]
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

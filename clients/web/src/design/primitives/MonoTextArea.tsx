import {
  forwardRef,
  type TextareaHTMLAttributes,
  type ReactNode,
  useId,
} from "react";

export interface MonoTextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  id?: string;
  labelText?: ReactNode;
  hideLabel?: boolean;
  helperText?: ReactNode;
  invalid?: boolean;
  invalidText?: ReactNode;
  rows?: number;
}

const wrapperStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "1px",
  lineHeight: "1.3",
  textTransform: "uppercase",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const textareaBaseStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  lineHeight: "1.55",
  color: "var(--frost-ink)",
  background: "transparent",
  border: "none",
  borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
  borderRadius: "0",
  padding: "8px 0",
  width: "100%",
  resize: "vertical",
  outline: "none",
};

const helperStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "0.4px",
  lineHeight: "1.3",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

const errorStyle: React.CSSProperties = {
  ...helperStyle,
  color: "var(--frost-spark)",
};

const focusCSS = `
  .frost-mono-textarea:focus-visible {
    outline: none;
    border-bottom: 1px solid var(--frost-ink) !important;
  }
  .frost-mono-textarea--error {
    border-bottom: 2px solid var(--frost-spark) !important;
  }
`;

export const MonoTextArea = forwardRef<HTMLTextAreaElement, MonoTextAreaProps>(
  function MonoTextArea(
    {
      id,
      labelText,
      hideLabel = false,
      helperText,
      invalid = false,
      invalidText,
      rows = 4,
      className,
      style,
      ...rest
    },
    ref,
  ) {
    const fallbackId = useId();
    const inputId = id ?? fallbackId;

    const textareaStyle: React.CSSProperties = {
      ...textareaBaseStyle,
      ...(invalid
        ? { borderBottom: "2px solid var(--frost-spark)" }
        : {}),
      ...style,
    };

    return (
      <>
        <style>{focusCSS}</style>
        <div style={wrapperStyle}>
          {labelText ? (
            <label
              htmlFor={inputId}
              style={
                hideLabel
                  ? { ...labelStyle, position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }
                  : labelStyle
              }
            >
              {labelText}
            </label>
          ) : null}
          <textarea
            ref={ref}
            id={inputId}
            className={[
              "frost-mono-textarea",
              invalid ? "frost-mono-textarea--error" : null,
              className,
            ]
              .filter(Boolean)
              .join(" ")}
            style={textareaStyle}
            rows={rows}
            aria-invalid={invalid || undefined}
            {...rest}
          />
          {invalid && invalidText ? (
            <div style={errorStyle}>{invalidText}</div>
          ) : helperText ? (
            <div style={helperStyle}>{helperText}</div>
          ) : null}
        </div>
      </>
    );
  },
);

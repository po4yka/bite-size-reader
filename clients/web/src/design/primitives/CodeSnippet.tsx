import { useState, type ReactNode } from "react";

export type CodeSnippetType = "single" | "multi" | "inline";

export interface CodeSnippetProps {
  type?: CodeSnippetType;
  feedback?: string;
  feedbackTimeout?: number;
  copyButtonDescription?: string;
  hideCopyButton?: boolean;
  ariaLabel?: string;
  className?: string;
  onClick?: () => void;
  children?: ReactNode;
}

export function CodeSnippet({
  type = "single",
  feedback = "Copied!",
  feedbackTimeout = 1200,
  hideCopyButton = false,
  ariaLabel = "Copy code",
  className,
  children,
}: CodeSnippetProps) {
  const [copied, setCopied] = useState(false);
  const text = typeof children === "string" ? children : String(children ?? "");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), feedbackTimeout);
    } catch {
      /* ignore clipboard errors */
    }
  };

  if (type === "inline") {
    return (
      <code
        className={className}
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "12px",
          fontWeight: 500,
          letterSpacing: "0.4px",
          background:
            "color-mix(in oklch, var(--frost-ink) 5%, var(--frost-page))",
          border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
          borderRadius: 0,
          padding: "0 4px",
        }}
      >
        {children}
      </code>
    );
  }

  return (
    <div
      className={className}
      style={{
        position: "relative",
        border: "1px solid var(--frost-ink)",
        borderRadius: 0,
        background:
          "color-mix(in oklch, var(--frost-ink) 5%, var(--frost-page))",
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      <pre
        style={{
          margin: 0,
          padding: "16px",
          fontSize: "12px",
          fontWeight: 500,
          letterSpacing: "0.4px",
          lineHeight: "130%",
          overflowX: "auto",
          paddingRight: hideCopyButton ? "16px" : "80px",
        }}
      >
        <code>{children}</code>
      </pre>
      {hideCopyButton ? null : (
        <button
          type="button"
          aria-label={ariaLabel}
          onClick={handleCopy}
          style={{
            position: "absolute",
            top: "8px",
            right: "8px",
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
          }}
        >
          [ {copied ? feedback : "COPY"} ]
        </button>
      )}
    </div>
  );
}

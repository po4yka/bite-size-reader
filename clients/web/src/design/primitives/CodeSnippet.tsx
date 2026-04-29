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
  feedbackTimeout = 2000,
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
      /* ignore */
    }
  };

  const cls = [
    "rtk-code-snippet",
    `rtk-code-snippet--${type}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  if (type === "inline") {
    return <code className={cls}>{children}</code>;
  }

  return (
    <div className={cls}>
      <pre className="rtk-code-snippet__code">
        <code>{children}</code>
      </pre>
      {hideCopyButton ? null : (
        <button
          type="button"
          aria-label={ariaLabel}
          onClick={handleCopy}
          className="rtk-code-snippet__copy"
        >
          {copied ? feedback : "Copy"}
        </button>
      )}
    </div>
  );
}

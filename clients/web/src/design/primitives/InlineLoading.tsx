import type { ReactNode } from "react";

export type InlineLoadingStatus =
  | "active"
  | "inactive"
  | "finished"
  | "error";

export interface InlineLoadingProps {
  status?: InlineLoadingStatus;
  description?: ReactNode;
  iconDescription?: string;
  successDelay?: number;
  onSuccess?: () => void;
  className?: string;
}

export function InlineLoading({
  status = "active",
  description,
  className,
}: InlineLoadingProps) {
  const cls = [
    "rtk-inline-loading",
    `rtk-inline-loading--${status}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div role="status" className={cls}>
      <span className="rtk-inline-loading__spinner" aria-hidden>
        {status === "active" ? "○" : status === "finished" ? "✓" : status === "error" ? "✕" : "·"}
      </span>
      {description ? (
        <span className="rtk-inline-loading__text">{description}</span>
      ) : null}
    </div>
  );
}

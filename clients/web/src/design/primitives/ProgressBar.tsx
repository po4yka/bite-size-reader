import type { ReactNode } from "react";

export type ProgressBarStatus = "active" | "finished" | "error";

export interface ProgressBarProps {
  label?: ReactNode;
  helperText?: ReactNode;
  hideLabel?: boolean;
  value?: number;
  max?: number;
  size?: "small" | "big";
  status?: ProgressBarStatus;
  type?: "default" | "indented" | "inline";
  className?: string;
}

export function ProgressBar({
  label,
  helperText,
  hideLabel = false,
  value,
  max = 100,
  size = "small",
  status = "active",
  className,
}: ProgressBarProps) {
  const isIndeterminate = value === undefined || value === null;
  const pct = isIndeterminate
    ? 0
    : Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));
  const cls = [
    "rtk-progress-bar",
    `rtk-progress-bar--${size}`,
    `rtk-progress-bar--${status}`,
    isIndeterminate ? "rtk-progress-bar--indeterminate" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      {label && !hideLabel ? (
        <div className="rtk-progress-bar__label">{label}</div>
      ) : null}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={isIndeterminate ? undefined : value}
        className="rtk-progress-bar__track"
      >
        <div
          className="rtk-progress-bar__fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      {helperText ? (
        <div className="rtk-progress-bar__helper">{helperText}</div>
      ) : null}
    </div>
  );
}

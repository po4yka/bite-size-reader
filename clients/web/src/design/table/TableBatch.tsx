import type { HTMLAttributes, ReactNode } from "react";

export interface TableBatchActionsProps extends HTMLAttributes<HTMLDivElement> {
  shouldShowBatchActions?: boolean;
  totalSelected?: number;
  onCancel?: () => void;
  cancelText?: ReactNode;
  totalCount?: number;
  translateWithId?: (id: string, args?: Record<string, unknown>) => string;
  children?: ReactNode;
}

export function TableBatchActions({
  shouldShowBatchActions = false,
  totalSelected = 0,
  onCancel,
  cancelText = "Cancel",
  className,
  children,
  ...rest
}: TableBatchActionsProps) {
  if (!shouldShowBatchActions) return null;
  // Strip any unknown render-prop fields from `rest` that aren't HTML attrs.
  const { translateWithId: _t, totalCount: _tc, ...divRest } =
    rest as TableBatchActionsProps;
  void _t;
  void _tc;
  return (
    <div
      className={[
        "rtk-table-batch-actions",
        "rtk-table-batch-actions--active",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...(divRest as HTMLAttributes<HTMLDivElement>)}
    >
      <span className="rtk-table-batch-actions__count">
        {totalSelected} selected
      </span>
      <div className="rtk-table-batch-actions__items">{children}</div>
      <button
        type="button"
        className="rtk-table-batch-actions__cancel"
        onClick={onCancel}
      >
        {cancelText}
      </button>
    </div>
  );
}

export interface TableBatchActionProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  renderIcon?: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  iconDescription?: string;
  children?: ReactNode;
}

export function TableBatchAction({
  renderIcon: RenderIcon,
  iconDescription,
  className,
  children,
  ...rest
}: TableBatchActionProps) {
  return (
    <button
      type="button"
      className={["rtk-table-batch-action", className].filter(Boolean).join(" ")}
      title={iconDescription}
      {...rest}
    >
      {RenderIcon ? <RenderIcon size={16} aria-hidden /> : null}
      {children}
    </button>
  );
}

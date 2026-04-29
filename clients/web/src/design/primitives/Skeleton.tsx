import type { CSSProperties } from "react";

export interface SkeletonTextProps {
  paragraph?: boolean;
  lineCount?: number;
  width?: string;
  heading?: boolean;
  className?: string;
}

export function SkeletonText({
  paragraph = false,
  lineCount = 3,
  width,
  heading = false,
  className,
}: SkeletonTextProps) {
  const lines = paragraph ? lineCount : 1;
  const style: CSSProperties | undefined = width ? { width } : undefined;
  return (
    <div
      className={["rtk-skeleton-text", className].filter(Boolean).join(" ")}
      aria-hidden
    >
      {Array.from({ length: lines }, (_, idx) => (
        <span
          key={idx}
          className={`rtk-skeleton rtk-skeleton--text${heading ? " rtk-skeleton--heading" : ""}`}
          style={style}
        />
      ))}
    </div>
  );
}

export interface SkeletonPlaceholderProps {
  className?: string;
}

export function SkeletonPlaceholder({ className }: SkeletonPlaceholderProps) {
  return (
    <div
      className={[
        "rtk-skeleton",
        "rtk-skeleton--placeholder",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-hidden
    />
  );
}

export interface DataTableSkeletonProps {
  columnCount?: number;
  rowCount?: number;
  showHeader?: boolean;
  showToolbar?: boolean;
  zebra?: boolean;
  compact?: boolean;
  headers?: Array<{ key?: string; header?: string } | string>;
  className?: string;
}

export function DataTableSkeleton({
  columnCount,
  rowCount = 5,
  showHeader = true,
  showToolbar = true,
  headers,
  className,
}: DataTableSkeletonProps) {
  const cols = headers?.length ?? columnCount ?? 3;
  return (
    <div
      className={["rtk-data-table-skeleton", className].filter(Boolean).join(" ")}
      aria-hidden
    >
      {showToolbar ? (
        <div className="rtk-data-table-skeleton__toolbar">
          <span className="rtk-skeleton rtk-skeleton--text" />
        </div>
      ) : null}
      <table className="rtk-data-table-skeleton__table">
        {showHeader ? (
          <thead>
            <tr>
              {Array.from({ length: cols }, (_, idx) => (
                <th key={idx}>
                  <span className="rtk-skeleton rtk-skeleton--text" />
                </th>
              ))}
            </tr>
          </thead>
        ) : null}
        <tbody>
          {Array.from({ length: rowCount }, (_, ridx) => (
            <tr key={ridx}>
              {Array.from({ length: cols }, (_, cidx) => (
                <td key={cidx}>
                  <span className="rtk-skeleton rtk-skeleton--text" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

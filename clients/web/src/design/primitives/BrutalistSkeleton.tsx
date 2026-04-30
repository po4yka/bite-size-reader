import { type CSSProperties } from "react";

/* ─── BrutalistSkeleton ─────────────────────────────────────────────────────── */

export interface BrutalistSkeletonProps {
  width?: string;
  height?: string;
  className?: string;
  style?: CSSProperties;
}

export function BrutalistSkeleton({ width, height, className, style }: BrutalistSkeletonProps) {
  return (
    <span
      aria-hidden
      className={["rtk-skeleton", className].filter(Boolean).join(" ")}
      style={{
        display: "block",
        borderRadius: "0",
        width: width ?? "100%",
        height: height ?? "1rem",
        ...style,
      }}
    />
  );
}

/* ─── BrutalistSkeletonText ─────────────────────────────────────────────────── */

export interface BrutalistSkeletonTextProps {
  paragraph?: boolean;
  lineCount?: number;
  width?: string;
  heading?: boolean;
  className?: string;
}

export function BrutalistSkeletonText({
  paragraph = false,
  lineCount = 3,
  width,
  heading = false,
  className,
}: BrutalistSkeletonTextProps) {
  const lines = paragraph ? lineCount : 1;
  const lineStyle: CSSProperties | undefined = width ? { width } : undefined;
  return (
    <div
      className={className}
      aria-hidden
    >
      {Array.from({ length: lines }, (_, idx) => (
        <span
          key={idx}
          className={`rtk-skeleton rtk-skeleton--text${heading ? " rtk-skeleton--heading" : ""}`}
          style={{ ...lineStyle, borderRadius: "0" }}
        />
      ))}
    </div>
  );
}

/* ─── BrutalistSkeletonPlaceholder ─────────────────────────────────────────── */

export interface BrutalistSkeletonPlaceholderProps {
  className?: string;
  style?: CSSProperties;
}

export function BrutalistSkeletonPlaceholder({ className, style }: BrutalistSkeletonPlaceholderProps) {
  return (
    <div
      className={["rtk-skeleton", "rtk-skeleton--placeholder", className]
        .filter(Boolean)
        .join(" ")}
      style={{ borderRadius: "0", ...style }}
      aria-hidden
    />
  );
}

/* ─── BrutalistDataTableSkeleton ────────────────────────────────────────────── */

export interface BrutalistDataTableSkeletonProps {
  columnCount?: number;
  rowCount?: number;
  showHeader?: boolean;
  showToolbar?: boolean;
  headers?: Array<{ key?: string; header?: string } | string>;
  className?: string;
}

const tableWrapStyle: CSSProperties = {
  border: "1px solid var(--frost-ink)",
  borderRadius: "0",
  width: "100%",
};

const headerCellStyle: CSSProperties = {
  padding: "8px",
  borderBottom: "1px solid var(--frost-ink)",
};

const dataCellStyle: CSSProperties = {
  padding: "8px",
};

const rowDividerStyle: CSSProperties = {
  borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)",
};

export function BrutalistDataTableSkeleton({
  columnCount,
  rowCount = 5,
  showHeader = true,
  showToolbar = true,
  headers,
  className,
}: BrutalistDataTableSkeletonProps) {
  const cols = headers?.length ?? columnCount ?? 3;
  return (
    <div
      className={className}
      aria-hidden
    >
      {showToolbar ? (
        <div style={{ marginBottom: "8px" }}>
          <span className="rtk-skeleton rtk-skeleton--text" style={{ width: "160px", borderRadius: "0" }} />
        </div>
      ) : null}
      <div style={tableWrapStyle}>
        <table style={{ width: "100%", borderCollapse: "collapse", borderRadius: "0" }}>
          {showHeader ? (
            <thead>
              <tr>
                {Array.from({ length: cols }, (_, idx) => (
                  <th key={idx} style={headerCellStyle}>
                    <span className="rtk-skeleton rtk-skeleton--text" style={{ borderRadius: "0" }} />
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {Array.from({ length: rowCount }, (_, ridx) => (
              <tr key={ridx} style={ridx < rowCount - 1 ? rowDividerStyle : undefined}>
                {Array.from({ length: cols }, (_, cidx) => (
                  <td key={cidx} style={dataCellStyle}>
                    <span className="rtk-skeleton rtk-skeleton--text" style={{ borderRadius: "0" }} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

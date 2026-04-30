import type { ReactNode } from "react";

export interface BracketPaginationChangeEvent {
  page: number;
  pageSize: number;
}

export interface BracketPaginationProps {
  page?: number;
  pageSize?: number;
  pageSizes?: number[];
  totalItems?: number;
  pageSizeInputDisabled?: boolean;
  itemsPerPageText?: ReactNode;
  pageRangeText?: (current: number, total: number) => ReactNode;
  itemRangeText?: (min: number, max: number, total: number) => ReactNode;
  onChange?: (event: BracketPaginationChangeEvent) => void;
  size?: "sm" | "md" | "lg";
  className?: string;
  disabled?: boolean;
  forwardText?: string;
  backwardText?: string;
}

const monoStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase" as const,
  letterSpacing: "1px",
  lineHeight: "130%",
};

const navBtnStyle = (disabled: boolean): React.CSSProperties => ({
  ...monoStyle,
  border: "1px solid var(--frost-ink)",
  borderRadius: 0,
  background: "var(--frost-page)",
  color: "var(--frost-ink)",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.4 : 1,
  padding: "6px 10px",
  lineHeight: 1,
});

const selectStyle: React.CSSProperties = {
  ...monoStyle,
  border: "none",
  borderBottom: "1px solid var(--frost-ink)",
  borderRadius: 0,
  background: "transparent",
  color: "var(--frost-ink)",
  padding: "4px 2px",
  cursor: "pointer",
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function BracketPagination({
  page = 1,
  pageSize = 10,
  pageSizes = [10, 20, 50],
  totalItems = 0,
  itemsPerPageText,
  onChange,
  className,
  disabled = false,
  forwardText = "Next page",
  backwardText = "Previous page",
}: BracketPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  const emit = (next: BracketPaginationChangeEvent) => {
    onChange?.(next);
  };

  return (
    <div
      className={className}
      role="navigation"
      aria-label="Pagination"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "12px",
        ...monoStyle,
      }}
    >
      {/* Items-per-page selector */}
      {pageSizes.length > 1 ? (
        <label style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          {itemsPerPageText ? (
            <span style={{ opacity: 0.55 }}>{itemsPerPageText}</span>
          ) : null}
          <select
            style={selectStyle}
            disabled={disabled}
            value={pageSize}
            onChange={(event) =>
              emit({ page: 1, pageSize: Number(event.currentTarget.value) })
            }
          >
            {pageSizes.map((s) => (
              <option key={s} value={s}>
                {pad(s)}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {/* Prev button */}
      <button
        type="button"
        aria-label={backwardText}
        disabled={disabled || page <= 1}
        onClick={() => emit({ page: Math.max(1, page - 1), pageSize })}
        style={navBtnStyle(disabled || page <= 1)}
      >
        [ &#8249; ]
      </button>

      {/* Page indicator */}
      <span style={{ opacity: 0.85 }}>
        PAGE {pad(page)} OF {pad(totalPages)}
      </span>

      {/* Next button */}
      <button
        type="button"
        aria-label={forwardText}
        disabled={disabled || page >= totalPages}
        onClick={() => emit({ page: Math.min(totalPages, page + 1), pageSize })}
        style={navBtnStyle(disabled || page >= totalPages)}
      >
        [ &#8250; ]
      </button>
    </div>
  );
}

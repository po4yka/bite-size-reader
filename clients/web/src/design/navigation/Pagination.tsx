import type { ReactNode } from "react";

export interface PaginationChangeEvent {
  page: number;
  pageSize: number;
}

export interface PaginationProps {
  page?: number;
  pageSize?: number;
  pageSizes?: number[];
  totalItems?: number;
  pageSizeInputDisabled?: boolean;
  itemsPerPageText?: ReactNode;
  pageRangeText?: (current: number, total: number) => ReactNode;
  itemRangeText?: (min: number, max: number, total: number) => ReactNode;
  onChange?: (event: PaginationChangeEvent) => void;
  size?: "sm" | "md" | "lg";
  className?: string;
  disabled?: boolean;
  forwardText?: string;
  backwardText?: string;
}

export function Pagination({
  page = 1,
  pageSize = 10,
  pageSizes = [10, 20, 50],
  totalItems = 0,
  itemsPerPageText = "Items per page:",
  onChange,
  className,
  disabled = false,
  forwardText = "Next page",
  backwardText = "Previous page",
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const startItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const endItem = Math.min(page * pageSize, totalItems);

  const emit = (next: PaginationChangeEvent) => {
    onChange?.(next);
  };

  return (
    <div
      className={["rtk-pagination", className].filter(Boolean).join(" ")}
      role="navigation"
      aria-label="Pagination"
    >
      <label className="rtk-pagination__page-size">
        <span>{itemsPerPageText}</span>
        <select
          disabled={disabled}
          value={pageSize}
          onChange={(event) =>
            emit({ page: 1, pageSize: Number(event.currentTarget.value) })
          }
        >
          {pageSizes.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <span className="rtk-pagination__range">
        {startItem}–{endItem} of {totalItems} items
      </span>
      <span className="rtk-pagination__page">
        Page {page} of {totalPages}
      </span>
      <button
        type="button"
        aria-label={backwardText}
        disabled={disabled || page <= 1}
        onClick={() => emit({ page: Math.max(1, page - 1), pageSize })}
        className="rtk-pagination__nav"
      >
        ‹
      </button>
      <button
        type="button"
        aria-label={forwardText}
        disabled={disabled || page >= totalPages}
        onClick={() => emit({ page: Math.min(totalPages, page + 1), pageSize })}
        className="rtk-pagination__nav"
      >
        ›
      </button>
    </div>
  );
}

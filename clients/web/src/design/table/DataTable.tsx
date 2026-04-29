import { useCallback, useMemo, useState, type ReactNode } from "react";

export interface DataTableHeader {
  key: string;
  header: ReactNode;
}

export interface DataTableRowInput {
  id: string;
  [key: string]: unknown;
}

export interface DataTableCell {
  id: string;
  value: unknown;
  isEditable: boolean;
  isEditing: boolean;
  isValid: boolean;
  errors: null;
  info: { header: string };
}

export interface DataTableRow extends DataTableRowInput {
  cells: DataTableCell[];
  isSelected?: boolean;
  isExpanded?: boolean;
  disabled?: boolean;
}

export interface DataTableRenderProps<
  R extends DataTableRowInput = DataTableRowInput,
  H extends DataTableHeader = DataTableHeader,
> {
  rows: DataTableRow[];
  headers: H[];
  selectedRows: DataTableRow[];
  getHeaderProps: (args: {
    header: H;
    isSortable?: boolean;
    onClick?: (event: React.MouseEvent) => void;
  }) => Record<string, unknown>;
  getRowProps: (args: { row: DataTableRow }) => Record<string, unknown>;
  getExpandHeaderProps: () => Record<string, unknown>;
  getExpandedRowProps: (args: { row: DataTableRow }) => Record<string, unknown>;
  getSelectionProps: (args?: { row?: DataTableRow }) => Record<string, unknown>;
  getToolbarProps: (
    args?: { onInputChange?: (value: string) => void },
  ) => Record<string, unknown>;
  getBatchActionProps: () => {
    shouldShowBatchActions: boolean;
    totalSelected: number;
    onCancel: () => void;
  };
  getTableProps: () => Record<string, unknown>;
  getTableContainerProps: () => Record<string, unknown>;
  getCellProps: (args: { cell: DataTableCell }) => Record<string, unknown>;
  /** Set the current search input. Useful for callers needing controlled search. */
  onInputChange: (value: string) => void;
  rowIds: string[];
  /** Returned for parity; provides simple sort no-ops. */
  sortBy: (headerKey: string) => void;
  /** Indicates whether the underlying data is still loading. Always false in shim. */
  isLoading: boolean;
  /** Source row prop (in case caller needs raw input). */
  __raw__: R[];
}

export type DataTableSortDirection = "ASC" | "DESC" | "NONE";

export interface DataTableProps<
  R extends DataTableRowInput = DataTableRowInput,
  H extends DataTableHeader = DataTableHeader,
> {
  rows: R[];
  headers: H[];
  isSortable?: boolean;
  radio?: boolean;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  useZebraStyles?: boolean;
  filterRows?: (args: {
    rowIds: string[];
    headers: H[];
    cellsById: Record<string, DataTableCell>;
    inputValue: string;
    getCellId: (rowId: string, headerKey: string) => string;
  }) => string[];
  children: (props: DataTableRenderProps<R, H>) => ReactNode;
}

/**
 * Render-prop DataTable mirroring the subset of the Carbon API used by the
 * existing call sites. Cell IDs use the `${row.id}:${header.key}` format so
 * `cell.id.split(":").pop()` extracts the header key.
 */
export function DataTable<
  R extends DataTableRowInput = DataTableRowInput,
  H extends DataTableHeader = DataTableHeader,
>(props: DataTableProps<R, H>) {
  const { rows: inputRows, headers, isSortable = false, radio = false, children, filterRows } =
    props;

  const [searchInput, setSearchInput] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const allRows = useMemo<DataTableRow[]>(() => {
    return inputRows.map((row) => {
      const cells: DataTableCell[] = headers.map((h) => ({
        id: `${row.id}:${h.key}`,
        value: (row as Record<string, unknown>)[h.key],
        isEditable: false,
        isEditing: false,
        isValid: true,
        errors: null,
        info: { header: h.key },
      }));
      return {
        ...row,
        cells,
        isSelected: selectedIds.has(row.id),
      } as DataTableRow;
    });
  }, [inputRows, headers, selectedIds]);

  const cellsById = useMemo(() => {
    const map: Record<string, DataTableCell> = {};
    for (const row of allRows) {
      for (const cell of row.cells) {
        map[cell.id] = cell;
      }
    }
    return map;
  }, [allRows]);

  const visibleRowIds = useMemo(() => {
    const allIds = allRows.map((r) => r.id);
    if (!searchInput.trim()) return allIds;
    if (filterRows) {
      return filterRows({
        rowIds: allIds,
        headers,
        cellsById,
        inputValue: searchInput,
        getCellId: (rowId, headerKey) => `${rowId}:${headerKey}`,
      });
    }
    const needle = searchInput.toLowerCase();
    return allIds.filter((id) =>
      headers.some((h) => {
        const cell = cellsById[`${id}:${h.key}`];
        if (cell == null) return false;
        return String(cell.value ?? "").toLowerCase().includes(needle);
      }),
    );
  }, [allRows, headers, cellsById, searchInput, filterRows]);

  const visibleRows = useMemo(
    () => allRows.filter((r) => visibleRowIds.includes(r.id)),
    [allRows, visibleRowIds],
  );

  const selectedRows = useMemo(
    () => allRows.filter((r) => selectedIds.has(r.id)),
    [allRows, selectedIds],
  );

  const toggleRow = useCallback((rowId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (radio) {
        next.clear();
        next.add(rowId);
        return next;
      }
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }, [radio]);

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === visibleRows.length) return new Set();
      return new Set(visibleRows.map((r) => r.id));
    });
  }, [visibleRows]);

  const renderProps: DataTableRenderProps<R, H> = {
    rows: visibleRows,
    headers,
    selectedRows,
    rowIds: visibleRows.map((r) => r.id),
    isLoading: false,
    __raw__: inputRows,
    getHeaderProps: ({ header, isSortable: headerSortable, onClick }) => ({
      key: header.key,
      isSortable: headerSortable ?? isSortable,
      onClick,
    }),
    getRowProps: ({ row }) => ({
      key: row.id,
      "data-row-id": row.id,
      isSelected: row.isSelected,
    }),
    getExpandHeaderProps: () => ({}),
    getExpandedRowProps: ({ row }) => ({
      key: `${row.id}-expanded`,
    }),
    getSelectionProps: (args) => {
      if (args?.row) {
        const row = args.row;
        return {
          id: `select-${row.id}`,
          name: `select-${row.id}`,
          checked: row.isSelected ?? false,
          onSelect: () => toggleRow(row.id),
          radio,
        };
      }
      const allSelected =
        visibleRows.length > 0 && selectedRows.length === visibleRows.length;
      return {
        id: "select-all",
        name: "select-all",
        checked: allSelected,
        onSelect: toggleAll,
      };
    },
    getToolbarProps: () => ({}),
    getBatchActionProps: () => ({
      shouldShowBatchActions: selectedRows.length > 0,
      totalSelected: selectedRows.length,
      onCancel: () => setSelectedIds(new Set()),
    }),
    getTableProps: () => ({
      isSortable,
      useZebraStyles: false,
    }),
    getTableContainerProps: () => ({}),
    getCellProps: ({ cell }) => ({
      key: cell.id,
    }),
    onInputChange: (value: string) => setSearchInput(value),
    sortBy: () => {
      /* sort visuals deferred to design-system phase */
    },
  };

  return <>{children(renderProps)}</>;
}

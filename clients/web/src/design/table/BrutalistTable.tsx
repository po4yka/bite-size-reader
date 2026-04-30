import {
  useCallback,
  useMemo,
  useState,
  type HTMLAttributes,
  type ReactNode,
  type TableHTMLAttributes,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";

/* ─── Shared types (preserved from DataTable + Table public surface) ────────── */

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
  onInputChange: (value: string) => void;
  rowIds: string[];
  sortBy: (headerKey: string) => void;
  isLoading: boolean;
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

/* ─── DataTable render-prop (Frost implementation) ──────────────────────────── */

export function DataTable<
  R extends DataTableRowInput = DataTableRowInput,
  H extends DataTableHeader = DataTableHeader,
>(props: DataTableProps<R, H>) {
  const {
    rows: inputRows,
    headers,
    isSortable = false,
    radio = false,
    children,
    filterRows,
  } = props;

  const [searchInput, setSearchInput] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<DataTableSortDirection>("NONE");

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
        isExpanded: expandedIds.has(row.id),
      } as DataTableRow;
    });
  }, [inputRows, headers, selectedIds, expandedIds]);

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

  const sortedAndFilteredRows = useMemo(() => {
    const filtered = allRows.filter((r) => visibleRowIds.includes(r.id));
    if (!sortKey || sortDir === "NONE") return filtered;
    return [...filtered].sort((a, b) => {
      const aCell = cellsById[`${a.id}:${sortKey}`];
      const bCell = cellsById[`${b.id}:${sortKey}`];
      const aVal = String(aCell?.value ?? "");
      const bVal = String(bCell?.value ?? "");
      const cmp = aVal.localeCompare(bVal);
      return sortDir === "ASC" ? cmp : -cmp;
    });
  }, [allRows, visibleRowIds, sortKey, sortDir, cellsById]);

  const selectedRows = useMemo(
    () => allRows.filter((r) => selectedIds.has(r.id)),
    [allRows, selectedIds],
  );

  const toggleRow = useCallback(
    (rowId: string) => {
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
    },
    [radio],
  );

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === sortedAndFilteredRows.length) return new Set();
      return new Set(sortedAndFilteredRows.map((r) => r.id));
    });
  }, [sortedAndFilteredRows]);

  const toggleExpand = useCallback((rowId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }, []);

  const handleSortBy = useCallback((headerKey: string) => {
    setSortKey((prevKey) => {
      if (prevKey !== headerKey) {
        setSortDir("ASC");
        return headerKey;
      }
      setSortDir((prevDir) => {
        if (prevDir === "NONE") return "ASC";
        if (prevDir === "ASC") return "DESC";
        return "NONE";
      });
      return headerKey;
    });
  }, []);

  const renderProps: DataTableRenderProps<R, H> = {
    rows: sortedAndFilteredRows,
    headers,
    selectedRows,
    rowIds: sortedAndFilteredRows.map((r) => r.id),
    isLoading: false,
    __raw__: inputRows,
    getHeaderProps: ({ header, isSortable: headerSortable, onClick }) => ({
      key: header.key,
      isSortable: headerSortable ?? isSortable,
      isSortHeader: sortKey === header.key,
      sortDirection: sortKey === header.key ? sortDir : "NONE",
      onClick: onClick ?? (() => handleSortBy(header.key)),
    }),
    getRowProps: ({ row }) => ({
      key: row.id,
      "data-row-id": row.id,
      isSelected: row.isSelected,
      isExpanded: row.isExpanded,
    }),
    getExpandHeaderProps: () => ({}),
    getExpandedRowProps: ({ row }) => ({
      key: `${row.id}-expanded`,
      onToggle: () => toggleExpand(row.id),
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
        sortedAndFilteredRows.length > 0 &&
        selectedRows.length === sortedAndFilteredRows.length;
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
    sortBy: handleSortBy,
  };

  return <>{children(renderProps)}</>;
}

/* ─── Table shell components (Frost reskin) ─────────────────────────────────── */

const ROW_DIVIDER = "color-mix(in oklch, var(--frost-ink) 50%, transparent)";
const HEADER_STYLE: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-xs-size)",
  fontWeight: 800,
  letterSpacing: "var(--frost-type-mono-xs-tracking)",
  lineHeight: "var(--frost-type-mono-xs-line-height)",
  textTransform: "uppercase",
  color: "var(--frost-ink)",
  backgroundColor: "var(--frost-page)",
  padding: "12px 16px",
  textAlign: "left",
  borderBottom: `1px solid ${ROW_DIVIDER}`,
};
const CELL_STYLE: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "var(--frost-type-mono-body-size)",
  fontWeight: "var(--frost-type-mono-body-weight)" as React.CSSProperties["fontWeight"],
  letterSpacing: "var(--frost-type-mono-body-tracking)",
  lineHeight: "var(--frost-type-mono-body-line-height)",
  color: "var(--frost-ink)",
  backgroundColor: "var(--frost-page)",
  padding: "12px 16px",
  borderBottom: `1px solid ${ROW_DIVIDER}`,
};

export interface TableContainerProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  stickyHeader?: boolean;
  useStaticWidth?: boolean;
  children?: ReactNode;
}

export function TableContainer({
  title,
  description,
  stickyHeader: _stickyHeader,
  useStaticWidth: _useStaticWidth,
  className,
  style,
  children,
  ...rest
}: TableContainerProps) {
  void _stickyHeader;
  void _useStaticWidth;
  return (
    <section
      className={["frost-table-container", className].filter(Boolean).join(" ")}
      style={{
        border: "var(--frost-hairline) solid var(--frost-ink)",
        borderRadius: 0,
        overflow: "hidden",
        ...style,
      }}
      {...rest}
    >
      {title || description ? (
        <header
          style={{
            padding: "12px 16px",
            borderBottom: `1px solid ${ROW_DIVIDER}`,
            backgroundColor: "var(--frost-page)",
          }}
        >
          {title ? (
            <div
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-emph-size)",
                fontWeight: 800,
                letterSpacing: "var(--frost-type-mono-emph-tracking)",
                textTransform: "uppercase",
                color: "var(--frost-ink)",
              }}
            >
              {title}
            </div>
          ) : null}
          {description ? (
            <div
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-body-size)",
                color: "var(--frost-ink)",
                opacity: 0.6,
                marginTop: 4,
              }}
            >
              {description}
            </div>
          ) : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  isSortable?: boolean;
  useZebraStyles?: boolean;
  children?: ReactNode;
}

export function Table({
  size: _size,
  isSortable: _isSortable,
  useZebraStyles: _useZebraStyles,
  className,
  style,
  children,
  ...rest
}: TableProps) {
  void _size;
  void _isSortable;
  void _useZebraStyles;
  return (
    <table
      className={["frost-table", className].filter(Boolean).join(" ")}
      style={{
        width: "100%",
        borderCollapse: "collapse",
        backgroundColor: "var(--frost-page)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </table>
  );
}

export function TableHead({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={["frost-table__head", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </thead>
  );
}

export function TableBody({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody
      className={["frost-table__body", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </tbody>
  );
}

export interface TableRowProps extends HTMLAttributes<HTMLTableRowElement> {
  isSelected?: boolean;
  isExpanded?: boolean;
  children?: ReactNode;
}

export function TableRow({
  isSelected: _isSelected,
  isExpanded: _isExpanded,
  className,
  children,
  ...rest
}: TableRowProps) {
  void _isSelected;
  void _isExpanded;
  return (
    <tr
      className={["frost-table__row", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </tr>
  );
}

export interface TableHeaderProps extends ThHTMLAttributes<HTMLTableCellElement> {
  scope?: "col" | "row";
  isSortable?: boolean;
  isSortHeader?: boolean;
  sortDirection?: DataTableSortDirection;
  onClick?: React.MouseEventHandler<HTMLTableCellElement>;
  children?: ReactNode;
}

export function TableHeader({
  scope = "col",
  isSortable,
  isSortHeader,
  sortDirection = "NONE",
  onClick,
  className,
  style,
  children,
  ...rest
}: TableHeaderProps) {
  const sortGlyph =
    isSortable && isSortHeader
      ? sortDirection === "ASC"
        ? " ▴"
        : sortDirection === "DESC"
          ? " ▾"
          : null
      : null;

  return (
    <th
      scope={scope}
      className={["frost-table__header", className].filter(Boolean).join(" ")}
      onClick={isSortable ? onClick : undefined}
      style={{
        ...HEADER_STYLE,
        cursor: isSortable ? "pointer" : "default",
        userSelect: isSortable ? "none" : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
      {isSortable ? (
        <span
          aria-hidden
          style={{
            opacity: isSortHeader && sortDirection !== "NONE" ? 1 : 0.4,
            marginLeft: 4,
          }}
        >
          {sortGlyph ?? (sortDirection === "ASC" ? "▴" : "▾")}
        </span>
      ) : null}
    </th>
  );
}

export interface TableCellProps extends TdHTMLAttributes<HTMLTableCellElement> {
  children?: ReactNode;
}

export function TableCell({
  className,
  style,
  children,
  ...rest
}: TableCellProps) {
  return (
    <td
      className={["frost-table__cell", className].filter(Boolean).join(" ")}
      style={{ ...CELL_STYLE, ...style }}
      {...rest}
    >
      {children}
    </td>
  );
}

/* ─── Mono checkbox cell (Group D will ship official Checkbox; inline for now) ─ */

export interface TableSelectCellProps {
  checked: boolean;
  onSelect: () => void;
  id: string;
  name?: string;
  radio?: boolean;
  disabled?: boolean;
}

export function TableSelectCell({
  checked,
  onSelect,
  id,
  name,
  radio = false,
  disabled = false,
}: TableSelectCellProps) {
  return (
    <td
      style={{
        ...CELL_STYLE,
        width: 48,
        textAlign: "center",
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      <label
        htmlFor={id}
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-body-size)",
          cursor: disabled ? "not-allowed" : "pointer",
          userSelect: "none",
        }}
      >
        <input
          type={radio ? "radio" : "checkbox"}
          id={id}
          name={name}
          checked={checked}
          onChange={onSelect}
          disabled={disabled}
          style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
          aria-label={radio ? "Select row" : checked ? "Deselect row" : "Select row"}
        />
        <span aria-hidden>{checked ? "[x]" : "[ ]"}</span>
      </label>
    </td>
  );
}

export interface TableSelectHeaderCellProps {
  checked: boolean;
  onSelect: () => void;
  id?: string;
}

export function TableSelectHeaderCell({
  checked,
  onSelect,
  id = "select-all",
}: TableSelectHeaderCellProps) {
  return (
    <th
      scope="col"
      style={{
        ...HEADER_STYLE,
        width: 48,
        textAlign: "center",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <label
        htmlFor={id}
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-xs-size)",
          fontWeight: 800,
          cursor: "pointer",
        }}
      >
        <input
          type="checkbox"
          id={id}
          checked={checked}
          onChange={onSelect}
          style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
          aria-label={checked ? "Deselect all rows" : "Select all rows"}
        />
        <span aria-hidden>{checked ? "[x]" : "[ ]"}</span>
      </label>
    </th>
  );
}

/* ─── Expand toggle cell ──────────────────────────────────────────────────────── */

export interface TableExpandCellProps {
  isExpanded: boolean;
  onToggle: () => void;
}

export function TableExpandCell({ isExpanded, onToggle }: TableExpandCellProps) {
  return (
    <td
      style={{
        ...CELL_STYLE,
        width: 40,
        textAlign: "center",
        cursor: "pointer",
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-label={isExpanded ? "Collapse row" : "Expand row"}
        style={{
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-body-size)",
          color: "var(--frost-ink)",
        }}
      >
        {isExpanded ? "▾" : "▸"}
      </button>
    </td>
  );
}

export function TableExpandHeaderCell() {
  return <th scope="col" style={{ ...HEADER_STYLE, width: 40 }} />;
}

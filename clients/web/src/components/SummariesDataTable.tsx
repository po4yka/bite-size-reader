import { type KeyboardEvent, type ReactNode, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  DataTable,
  DataTableSkeleton,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  Tag,
} from "../design";
import type { SummaryCompact } from "../api/types";
import { QueryErrorNotification } from "./QueryErrorNotification";

interface SummariesDataTableProps {
  summaries: SummaryCompact[];
  headers: Array<{ key: string; header: string }>;
  pagination: {
    total: number;
    page: number;
    pageSize: number;
    pageSizes?: number[];
    onChange: (event: { page: number; pageSize: number }) => void;
  };
  searchTerm: string;
  onSearchChange: (value: string) => void;
  isLoading: boolean;
  error: unknown;
  title: string;
  renderActions?: (summary: SummaryCompact) => ReactNode;
  renderStatusColumn?: (summary: SummaryCompact) => ReactNode;
}

export function SummariesDataTable({
  summaries,
  headers,
  pagination,
  searchTerm,
  onSearchChange,
  isLoading,
  error,
  title,
  renderActions,
  renderStatusColumn,
}: SummariesDataTableProps) {
  const navigate = useNavigate();

  const filteredSummaries = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) return summaries;
    return summaries.filter(
      (s) =>
        s.title.toLowerCase().includes(query) ||
        s.domain.toLowerCase().includes(query) ||
        s.topicTags.join(" ").toLowerCase().includes(query),
    );
  }, [searchTerm, summaries]);

  const summaryMap = useMemo(
    () => new Map(filteredSummaries.map((s) => [String(s.id), s])),
    [filteredSummaries],
  );

  const rows = filteredSummaries.map((summary) => ({
    id: String(summary.id),
    title: summary.title,
    domain: summary.domain,
    readingTimeMin: `${summary.readingTimeMin}m`,
    topicTags: summary.topicTags.join(", "),
    createdAt: new Date(summary.createdAt).toLocaleDateString(),
    // Slot keys carry the summary object for custom cell rendering
    actions: summary,
    status: summary,
  }));

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, rowId: string): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    navigate(`/library/${rowId}`);
  }

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load summaries" />

      {isLoading ? (
        <DataTableSkeleton columnCount={headers.length} rowCount={8} showToolbar />
      ) : (
        <>
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps, getToolbarProps }) => (
              <TableContainer title={title}>
                <TableToolbar {...getToolbarProps()}>
                  <TableToolbarContent>
                    <TableToolbarSearch
                      persistent
                      onInput={(event) => onSearchChange((event.target as HTMLInputElement).value)}
                      value={searchTerm}
                    />
                  </TableToolbarContent>
                </TableToolbar>
                <Table {...getTableProps()}>
                  <TableHead>
                    <TableRow>
                      {headers.map((header) => (
                        <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const summary = summaryMap.get(row.id);
                      if (!summary) return null;
                      return (
                        <TableRow
                          {...getRowProps({ row })}
                          onClick={() => navigate(`/library/${row.id}`)}
                          onKeyDown={(event) => handleRowKeyDown(event, row.id)}
                          role="link"
                          tabIndex={0}
                          className="clickable-row"
                        >
                          {row.cells.map((cell) => {
                            const headerKey = cell.id.split(":").pop();
                            if (headerKey === "topicTags") {
                              return (
                                <TableCell key={cell.id}>
                                  <div className="tag-row">
                                    {summary.topicTags.slice(0, 3).map((topic) => (
                                      <Tag key={topic} >{topic}</Tag>
                                    ))}
                                  </div>
                                </TableCell>
                              );
                            }
                            if (headerKey === "actions" && renderActions) {
                              return (
                                <TableCell key={cell.id}>
                                  {renderActions(summary)}
                                </TableCell>
                              );
                            }
                            if (headerKey === "status" && renderStatusColumn) {
                              return (
                                <TableCell key={cell.id}>
                                  {renderStatusColumn(summary)}
                                </TableCell>
                              );
                            }
                            return <TableCell key={cell.id}>{cell.value as string}</TableCell>;
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>

          <Pagination
            page={pagination.page}
            pageSize={pagination.pageSize}
            pageSizes={pagination.pageSizes ?? [10, 20, 50]}
            totalItems={pagination.total}
            onChange={pagination.onChange}
          />
        </>
      )}
    </>
  );
}

import { useCallback, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  DataTable,
  DataTableSkeleton,
  InlineNotification,
  Pagination,
  Select,
  SelectItem,
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
} from "@carbon/react";
import { fetchSummaries } from "../../api/summaries";
import type { SummaryCompact } from "../../api/types";

const SORT_OPTIONS = [
  { value: "created_at_desc", label: "Newest first" },
  { value: "created_at_asc", label: "Oldest first" },
] as const;

type SortOption = (typeof SORT_OPTIONS)[number]["value"];

export default function ArticlesPage() {
  const navigate = useNavigate();

  const [sort, setSort] = useState<SortOption>("created_at_desc");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const summariesQuery = useQuery({
    queryKey: ["all-articles", sort, page, pageSize],
    queryFn: () =>
      fetchSummaries({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        sort,
      }),
  });

  const filteredRows = useMemo(() => {
    const rows = summariesQuery.data?.summaries ?? [];
    const query = searchTerm.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) => {
      return (
        row.title.toLowerCase().includes(query) ||
        row.domain.toLowerCase().includes(query) ||
        row.topicTags.join(" ").toLowerCase().includes(query)
      );
    });
  }, [searchTerm, summariesQuery.data?.summaries]);

  const headers: Array<{ key: keyof SummaryCompact | "status"; header: string }> = [
    { key: "title", header: "Title" },
    { key: "domain", header: "Domain" },
    { key: "readingTimeMin", header: "Read Time" },
    { key: "createdAt", header: "Created" },
    { key: "status", header: "Status" },
  ];

  const rows = filteredRows.map((summary) => ({
    id: String(summary.id),
    title: summary.title,
    domain: summary.domain,
    readingTimeMin: `${summary.readingTimeMin}m`,
    createdAt: new Date(summary.createdAt).toLocaleDateString(),
    status: summary,
  }));

  const handleRowKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTableRowElement>, rowId: string): void => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      navigate(`/library/${rowId}`);
    },
    [navigate],
  );

  const isInitialLoading = summariesQuery.isLoading && !summariesQuery.data;

  return (
    <section className="page-section">
      <h1>All Articles</h1>
      <p className="page-subtitle">Browse all saved article summaries and sort the list.</p>

      <div className="articles-controls">
        <Select
          id="articles-sort"
          labelText="Sort"
          value={sort}
          onChange={(event) => {
            setSort(event.currentTarget.value as SortOption);
            setPage(1);
          }}
        >
          {SORT_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value} text={option.label} />
          ))}
        </Select>
      </div>

      {summariesQuery.error && (
        <InlineNotification
          kind="error"
          title="Failed to load articles"
          subtitle={summariesQuery.error instanceof Error ? summariesQuery.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {isInitialLoading ? (
        <DataTableSkeleton columnCount={headers.length} rowCount={8} showToolbar />
      ) : (
        <>
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps, getToolbarProps }) => (
              <TableContainer title="All article summaries">
                <TableToolbar {...getToolbarProps()}>
                  <TableToolbarContent>
                    <TableToolbarSearch
                      persistent
                      onInput={(event) => {
                        const value = (event.target as HTMLInputElement).value;
                        setSearchTerm(value);
                      }}
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
                      const cellValue = row.cells.find((cell) => cell.info.header === "Status")?.value;
                      if (!cellValue || typeof cellValue !== "object") return null;
                      const summary = cellValue as SummaryCompact;
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
                            if (cell.info.header === "Status") {
                              return (
                                <TableCell key={cell.id}>
                                  <div className="tag-row">
                                    <Tag type={summary.isRead ? "green" : "gray"}>
                                      {summary.isRead ? "Read" : "Unread"}
                                    </Tag>
                                    {summary.isFavorited && <Tag type="magenta">Favorited</Tag>}
                                  </div>
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

          {summariesQuery.data && (
            <Pagination
              page={page}
              pageSize={pageSize}
              pageSizes={[10, 20, 50]}
              totalItems={summariesQuery.data.pagination.total}
              onChange={(event) => {
                setPage(event.page);
                setPageSize(event.pageSize);
              }}
            />
          )}
        </>
      )}
    </section>
  );
}

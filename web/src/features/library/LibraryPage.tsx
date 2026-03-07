import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  InlineLoading,
  InlineNotification,
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
} from "@carbon/react";
import { fetchSummaries, toggleSummaryFavorite } from "../../api/summaries";
import type { SummaryCompact } from "../../api/types";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "favorites", label: "Favorites" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

export default function LibraryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [filter, setFilter] = useState<FilterKey>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const summariesQuery = useQuery({
    queryKey: ["summaries", filter, page, pageSize],
    queryFn: () =>
      fetchSummaries({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        isRead: filter === "unread" ? false : undefined,
        isFavorited: filter === "favorites" ? true : undefined,
        sort: "created_at_desc",
      }),
  });

  const favoriteMutation = useMutation({
    mutationFn: (summaryId: number) => toggleSummaryFavorite(summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["summaries"] });
    },
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

  const headers: Array<{ key: keyof SummaryCompact | "actions"; header: string }> = [
    { key: "title", header: "Title" },
    { key: "domain", header: "Domain" },
    { key: "readingTimeMin", header: "Read Time" },
    { key: "topicTags", header: "Topics" },
    { key: "createdAt", header: "Created" },
    { key: "actions", header: "Actions" },
  ];

  const rows = filteredRows.map((summary) => ({
    id: String(summary.id),
    title: summary.title,
    domain: summary.domain,
    readingTimeMin: `${summary.readingTimeMin}m`,
    topicTags: summary.topicTags.join(", "),
    createdAt: new Date(summary.createdAt).toLocaleDateString(),
    actions: summary,
  }));

  return (
    <section className="page-section">
      <h1>Library</h1>

      <div className="filter-row">
        {FILTERS.map((entry) => (
          <button
            key={entry.key}
            className="filter-chip"
            data-active={entry.key === filter}
            onClick={() => {
              setFilter(entry.key);
              setPage(1);
            }}
            type="button"
          >
            <Tag type={entry.key === filter ? "blue" : "gray"}>{entry.label}</Tag>
          </button>
        ))}
      </div>

      {summariesQuery.isLoading && <InlineLoading description="Loading summaries..." />}

      {summariesQuery.error && (
        <InlineNotification
          kind="error"
          title="Failed to load summaries"
          subtitle={summariesQuery.error instanceof Error ? summariesQuery.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      <DataTable rows={rows} headers={headers}>
        {({ rows, headers, getHeaderProps, getRowProps, getTableProps, getToolbarProps }) => (
          <TableContainer title="Article summaries">
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
                    <TableHeader {...getHeaderProps({ header })}>
                      {header.header}
                    </TableHeader>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => {
                  const summary = row.cells.find((cell) => cell.info.header === "Actions")?.value as SummaryCompact;
                  return (
                    <TableRow
                      {...getRowProps({ row })}
                      onClick={() => navigate(`/library/${row.id}`)}
                      className="clickable-row"
                    >
                      {row.cells.map((cell) => {
                        if (cell.info.header === "Topics") {
                          return (
                            <TableCell key={cell.id}>
                              <div className="tag-row">
                                {summary.topicTags.slice(0, 3).map((topic) => (
                                  <Tag key={topic} type="teal">
                                    {topic}
                                  </Tag>
                                ))}
                              </div>
                            </TableCell>
                          );
                        }

                        if (cell.info.header === "Actions") {
                          return (
                            <TableCell key={cell.id}>
                              <Button
                                kind={summary.isFavorited ? "primary" : "ghost"}
                                size="sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  favoriteMutation.mutate(summary.id);
                                }}
                              >
                                {summary.isFavorited ? "Favorited" : "Favorite"}
                              </Button>
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
        page={page}
        pageSize={pageSize}
        pageSizes={[10, 20, 50]}
        totalItems={summariesQuery.data?.pagination.total ?? 0}
        onChange={(event) => {
          setPage(event.page);
          setPageSize(event.pageSize);
        }}
      />
    </section>
  );
}

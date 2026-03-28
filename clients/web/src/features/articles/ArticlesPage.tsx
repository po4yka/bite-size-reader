import { useState } from "react";
import { Select, SelectItem, Tag } from "@carbon/react";
import { useSummariesList } from "../../hooks/useSummaries";
import type { SummaryCompact } from "../../api/types";
import { SummariesDataTable } from "../../components/SummariesDataTable";

const SORT_OPTIONS = [
  { value: "created_at_desc", label: "Newest first" },
  { value: "created_at_asc", label: "Oldest first" },
] as const;

type SortOption = (typeof SORT_OPTIONS)[number]["value"];

const HEADERS: Array<{ key: string; header: string }> = [
  { key: "title", header: "Title" },
  { key: "domain", header: "Domain" },
  { key: "readingTimeMin", header: "Read Time" },
  { key: "createdAt", header: "Created" },
  { key: "status", header: "Status" },
];

export default function ArticlesPage() {
  const [sort, setSort] = useState<SortOption>("created_at_desc");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const summariesQuery = useSummariesList({
    limit: pageSize,
    offset: (page - 1) * pageSize,
    sort,
  });

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

      <SummariesDataTable
        summaries={summariesQuery.data?.summaries ?? []}
        headers={HEADERS}
        pagination={{
          total: summariesQuery.data?.pagination.total ?? 0,
          page,
          pageSize,
          pageSizes: [10, 20, 50],
          onChange: (event) => {
            setPage(event.page);
            setPageSize(event.pageSize);
          },
        }}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        isLoading={summariesQuery.isLoading && !summariesQuery.data}
        error={summariesQuery.error}
        title="All article summaries"
        renderStatusColumn={(summary: SummaryCompact) => (
          <div className="tag-row">
            <Tag type={summary.isRead ? "green" : "gray"}>
              {summary.isRead ? "Read" : "Unread"}
            </Tag>
            {summary.isFavorited && <Tag type="magenta">Favorited</Tag>}
          </div>
        )}
      />
    </section>
  );
}

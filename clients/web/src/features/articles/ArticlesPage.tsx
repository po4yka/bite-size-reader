import { useState } from "react";
import { MonoSelect, MonoSelectItem, Tag } from "../../design";
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
    <main
      style={{
        maxWidth: "var(--frost-strip-7)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-page)" }}>
        <div>
          <h1
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-emph-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "var(--frost-ink)",
              margin: "0 0 8px 0",
            }}
          >
            All Articles
          </h1>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: 0,
            }}
          >
            Browse all saved article summaries and sort the list.
          </p>
        </div>

        <div style={{ maxWidth: "240px" }}>
          <MonoSelect
            id="articles-sort"
            labelText="Sort"
            value={sort}
            onChange={(event) => {
              setSort(event.currentTarget.value as SortOption);
              setPage(1);
            }}
          >
            {SORT_OPTIONS.map((option) => (
              <MonoSelectItem key={option.value} value={option.value} text={option.label} />
            ))}
          </MonoSelect>
        </div>
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
            <Tag>
              {summary.isRead ? "Read" : "Unread"}
            </Tag>
            {summary.isFavorited && <Tag>Favorited</Tag>}
          </div>
        )}
      />
    </main>
  );
}

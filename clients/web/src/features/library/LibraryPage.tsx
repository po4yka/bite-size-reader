import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BracketButton, BrutalistCard } from "../../design";
import { useSummariesList, useToggleFavorite } from "../../hooks/useSummaries";
import type { SummaryCompact } from "../../api/types";
import { SummariesDataTable } from "../../components/SummariesDataTable";
import AddToCollectionModal from "../../components/AddToCollectionModal";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "favorites", label: "Favorites" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

const HEADERS: Array<{ key: string; header: string }> = [
  { key: "title", header: "Title" },
  { key: "domain", header: "Domain" },
  { key: "readingTimeMin", header: "Read Time" },
  { key: "topicTags", header: "Topics" },
  { key: "createdAt", header: "Created" },
  { key: "actions", header: "Actions" },
];

export default function LibraryPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterKey>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [collectionModalSummaryId, setCollectionModalSummaryId] = useState<number | null>(null);

  const summariesQuery = useSummariesList({
    limit: pageSize,
    offset: (page - 1) * pageSize,
    isRead: filter === "unread" ? false : undefined,
    isFavorited: filter === "favorites" ? true : undefined,
    sort: "created_at_desc",
  });

  const favoriteMutation = useToggleFavorite();

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
        <h1
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: "var(--frost-type-mono-emph-size)",
            fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
            letterSpacing: "var(--frost-type-mono-emph-tracking)",
            textTransform: "uppercase",
            color: "var(--frost-ink)",
            margin: 0,
          }}
        >
          Library
        </h1>

        <div
          className="filter-row"
          role="radiogroup"
          aria-label="Filter articles"
          style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}
        >
          {FILTERS.map((entry) => (
            <BracketButton
              key={entry.key}
              kind="ghost"
              size="sm"
              role="radio"
              aria-checked={entry.key === filter}
              style={entry.key === filter ? { background: "var(--frost-ink)", color: "var(--frost-page)" } : undefined}
              onClick={() => {
                setFilter(entry.key);
                setPage(1);
              }}
            >
              {entry.label}
            </BracketButton>
          ))}
        </div>
      </div>

      {!summariesQuery.isLoading &&
      !summariesQuery.error &&
      (summariesQuery.data?.summaries.length ?? 0) === 0 ? (
        <BrutalistCard>
          <div className="page-heading-group">
            <h3
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-emph-size)",
                fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                textTransform: "uppercase",
                letterSpacing: "var(--frost-type-mono-emph-tracking)",
                color: "var(--frost-ink)",
                margin: 0,
              }}
            >
              No articles yet
            </h3>
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-body-size)",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                margin: 0,
              }}
            >
              Submit a URL or forward a Telegram message to start building your library.
            </p>
          </div>
          <div className="form-actions">
            <BracketButton kind="primary" size="sm" onClick={() => navigate("/submit")}>
              Submit your first article
            </BracketButton>
          </div>
        </BrutalistCard>
      ) : (
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
          title="Article summaries"
          renderActions={(summary: SummaryCompact) => (
            <div className="table-actions">
              <BracketButton
                kind={summary.isFavorited ? "primary" : "ghost"}
                size="sm"
                style={summary.isFavorited ? { background: "var(--frost-ink)", color: "var(--frost-page)" } : undefined}
                onClick={(event) => {
                  event.stopPropagation();
                  favoriteMutation.mutate(summary.id);
                }}
              >
                {summary.isFavorited ? "Favorited" : "Favorite"}
              </BracketButton>
              <BracketButton
                kind="tertiary"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation();
                  setCollectionModalSummaryId(summary.id);
                }}
              >
                Add to collection
              </BracketButton>
            </div>
          )}
        />
      )}

      <AddToCollectionModal
        open={collectionModalSummaryId != null}
        summaryId={collectionModalSummaryId}
        onClose={() => setCollectionModalSummaryId(null)}
      />
    </main>
  );
}

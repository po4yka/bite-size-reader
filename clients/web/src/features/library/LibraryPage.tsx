import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Tag, Tile } from "../../design";
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
    <section className="page-section">
      <h1>Library</h1>

      <div className="filter-row" role="radiogroup" aria-label="Filter articles">
        {FILTERS.map((entry) => (
          <Button
            key={entry.key}
            kind="ghost"
            size="sm"
            className="filter-chip"
            role="radio"
            aria-checked={entry.key === filter}
            onClick={() => {
              setFilter(entry.key);
              setPage(1);
            }}
          >
            <Tag type={entry.key === filter ? "blue" : "gray"}>{entry.label}</Tag>
          </Button>
        ))}
      </div>

      {!summariesQuery.isLoading &&
      !summariesQuery.error &&
      (summariesQuery.data?.summaries.length ?? 0) === 0 ? (
        <Tile>
          <div className="page-heading-group">
            <h3>No articles yet</h3>
            <p className="page-subtitle">
              Submit a URL or forward a Telegram message to start building your library.
            </p>
          </div>
          <div className="form-actions">
            <Button kind="primary" size="sm" onClick={() => navigate("/submit")}>
              Submit your first article
            </Button>
          </div>
        </Tile>
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
              <Button
                kind="tertiary"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation();
                  setCollectionModalSummaryId(summary.id);
                }}
              >
                Add to collection
              </Button>
            </div>
          )}
        />
      )}

      <AddToCollectionModal
        open={collectionModalSummaryId != null}
        summaryId={collectionModalSummaryId}
        onClose={() => setCollectionModalSummaryId(null)}
      />
    </section>
  );
}

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  BracketButton,
  BracketSearch,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoSelect,
  MonoSelectItem,
  StatusBadge,
} from "../../design";
import { fetchRepositories, searchRepositories } from "../../api/repositories";
import type { RepositoryCompact, RepositoryListSort, RepositorySource } from "../../api/repositories";
import IngestRepositoryDialog from "./IngestRepositoryDialog";

const ROW_ESTIMATE_PX = 60;
const PAGE_SIZE = 50;

const SORT_OPTIONS: { value: RepositoryListSort; label: string }[] = [
  { value: "stars_desc", label: "Stars" },
  { value: "pushed_desc", label: "Recently pushed" },
  { value: "created_desc", label: "Recently added" },
  { value: "full_name_asc", label: "Name A-Z" },
];

const sectionLabel: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

function LanguageChip({ lang }: { lang: string }) {
  return (
    <span
      style={{
        fontFamily: "var(--frost-font-mono)",
        fontSize: "10px",
        fontWeight: 800,
        letterSpacing: "0.8px",
        textTransform: "uppercase",
        border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
        padding: "1px 5px",
        whiteSpace: "nowrap",
      }}
    >
      {lang}
    </span>
  );
}

function RepoRow({
  repo,
  isActive,
  onHover,
  onClick,
}: {
  repo: RepositoryCompact;
  isActive: boolean;
  onHover: () => void;
  onClick: () => void;
}) {
  return (
    <li
      onClick={onClick}
      onMouseEnter={onHover}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, 1fr) 80px 48px minmax(80px, 200px) 80px",
        gap: "0 var(--frost-line, 16px)",
        alignItems: "start",
        padding: "10px 0",
        borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)",
        cursor: "pointer",
        background: isActive
          ? "color-mix(in oklch, var(--frost-ink) 6%, transparent)"
          : "transparent",
        fontFamily: "var(--frost-font-mono)",
      }}
    >
      {/* full_name + description */}
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "13px",
            fontWeight: 800,
            letterSpacing: "0.4px",
            color: "var(--frost-ink)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {repo.full_name}
          {repo.is_starred && (
            <span
              aria-label="Starred"
              style={{ marginLeft: "6px", fontSize: "11px", opacity: 0.6 }}
            >
              ★
            </span>
          )}
        </div>
        {repo.description && (
          <div
            style={{
              fontSize: "11px",
              fontWeight: 500,
              letterSpacing: "0.3px",
              color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              marginTop: "2px",
            }}
          >
            {repo.description}
          </div>
        )}
        {repo.topics.length > 0 && (
          <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" }}>
            {repo.topics.slice(0, 3).map((t) => (
              <span
                key={t}
                style={{
                  fontSize: "10px",
                  fontWeight: 500,
                  letterSpacing: "0.5px",
                  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                  textTransform: "uppercase",
                }}
              >
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* language */}
      <div style={{ paddingTop: "1px" }}>
        {repo.primary_language ? (
          <LanguageChip lang={repo.primary_language} />
        ) : (
          <span style={{ opacity: 0.3, fontSize: "11px" }}>—</span>
        )}
      </div>

      {/* stars */}
      <div
        style={{
          fontSize: "12px",
          fontWeight: 500,
          color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
          textAlign: "right",
          paddingTop: "1px",
        }}
      >
        {repo.stars >= 1000
          ? `${(repo.stars / 1000).toFixed(1)}k`
          : String(repo.stars)}
      </div>

      {/* topics overflow */}
      <div />

      {/* badges */}
      <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", paddingTop: "1px" }}>
        {repo.pending_analysis && (
          <StatusBadge severity="warn" title="Indexing" />
        )}
        {repo.is_archived && (
          <StatusBadge severity="info" title="Archived" />
        )}
      </div>
    </li>
  );
}

export default function RepositoriesPage() {
  const navigate = useNavigate();
  const parentRef = useRef<HTMLDivElement>(null);

  const [ingestOpen, setIngestOpen] = useState(false);
  const [filterSource, setFilterSource] = useState<RepositorySource | "all">("all");
  const [filterLanguage, setFilterLanguage] = useState("");
  const [sort, setSort] = useState<RepositoryListSort>("stars_desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const isSearchMode = searchQuery.trim().length >= 2;

  // List mode (infinite query)
  const listQuery = useInfiniteQuery({
    queryKey: ["repositories", filterSource, filterLanguage, sort],
    queryFn: ({ pageParam = 0 }) =>
      fetchRepositories({
        source: filterSource !== "all" ? filterSource : undefined,
        language: filterLanguage || undefined,
        sort,
        limit: PAGE_SIZE,
        offset: pageParam as number,
      }),
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.repositories.length, 0);
      return loaded < last.pagination.total ? loaded : undefined;
    },
    initialPageParam: 0,
    enabled: !isSearchMode,
  });

  // Search mode (single query, re-runs on query change)
  const searchQueryResult = useInfiniteQuery({
    queryKey: ["repositories-search", searchQuery],
    queryFn: ({ pageParam = 0 }) =>
      searchRepositories({ q: searchQuery, limit: PAGE_SIZE, offset: pageParam as number }),
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.results.length, 0);
      return loaded < last.pagination.total ? loaded : undefined;
    },
    initialPageParam: 0,
    enabled: isSearchMode,
  });

  const activeQuery = isSearchMode ? searchQueryResult : listQuery;

  const repos: RepositoryCompact[] = isSearchMode
    ? (searchQueryResult.data?.pages.flatMap((p) => p.results) ?? [])
    : (listQuery.data?.pages.flatMap((p) => p.repositories) ?? []);

  const total = isSearchMode
    ? (searchQueryResult.data?.pages[0]?.pagination.total ?? 0)
    : (listQuery.data?.pages[0]?.pagination.total ?? 0);

  // eslint-disable-next-line
  const rowVirtualizer = useVirtualizer({
    count: repos.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_ESTIMATE_PX,
    overscan: 8,
  });

  // Fetch more when scrolling near the end
  const virtualItems = rowVirtualizer.getVirtualItems();
  useEffect(() => {
    if (!virtualItems.length) return;
    const last = virtualItems[virtualItems.length - 1];
    if (last && last.index >= repos.length - 5 && activeQuery.hasNextPage && !activeQuery.isFetchingNextPage) {
      void activeQuery.fetchNextPage();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [virtualItems, repos.length, activeQuery.hasNextPage, activeQuery.isFetchingNextPage]);

  useEffect(() => {
    if (repos.length > 0) setCursor((c) => Math.min(c, repos.length - 1));
  }, [repos.length]);

  const isLoading = activeQuery.isLoading && !activeQuery.data;

  return (
    <main
      style={{
        maxWidth: "var(--frost-strip-7, 1232px)",
        padding: "0 var(--frost-pad-page, 32px)",
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "var(--frost-line, 16px) 0",
          borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
          gap: "var(--frost-line, 16px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={sectionLabel}>Repositories</span>
          <span
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "11px",
              fontWeight: 500,
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
            }}
          >
            {total} total
          </span>
        </div>
        <BracketButton
          size="sm"
          aria-label="Add repository"
          onClick={() => setIngestOpen(true)}
        >
          + Add
        </BracketButton>
      </div>

      {/* Search + filters row */}
      <div
        className="repo-filters"
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: "12px",
          padding: "var(--frost-half-line, 8px) 0",
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: "1 1 200px", minWidth: "160px" }}>
          <BracketSearch
            id="repo-search"
            labelText="Search repositories"
            placeholder="SEARCH (2+ CHARS FOR SEMANTIC)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
          />
        </div>

        {/* Filter chips */}
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {(["all", "starred", "manual"] as const).map((src) => (
            <button
              key={src}
              onClick={() => setFilterSource(src)}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "11px",
                fontWeight: 800,
                letterSpacing: "1px",
                textTransform: "uppercase",
                border: "1px solid var(--frost-ink)",
                borderLeft:
                  filterSource === src
                    ? "2px solid var(--frost-ink)"
                    : "1px solid var(--frost-ink)",
                background:
                  filterSource === src ? "var(--frost-ink)" : "var(--frost-page)",
                color:
                  filterSource === src ? "var(--frost-page)" : "var(--frost-ink)",
                padding: "3px 10px",
                cursor: "pointer",
                transition: "background 0.08s linear, color 0.08s linear",
              }}
              aria-pressed={filterSource === src}
            >
              {src === "all" ? "All" : src === "starred" ? "Starred" : "Manual"}
            </button>
          ))}
        </div>

        {/* Language filter */}
        <div style={{ width: "120px" }}>
          <MonoSelect
            id="repo-lang"
            labelText="Language"
            value={filterLanguage}
            onChange={(e) => setFilterLanguage(e.currentTarget.value)}
          >
            <MonoSelectItem value="" text="All" />
            {["TypeScript", "Python", "Rust", "Go", "JavaScript", "Java", "C++", "C#"].map((l) => (
              <MonoSelectItem key={l} value={l} text={l} />
            ))}
          </MonoSelect>
        </div>

        {/* Sort */}
        <div style={{ width: "160px" }}>
          <MonoSelect
            id="repo-sort"
            labelText="Sort"
            value={sort}
            onChange={(e) => setSort(e.currentTarget.value as RepositoryListSort)}
          >
            {SORT_OPTIONS.map((o) => (
              <MonoSelectItem key={o.value} value={o.value} text={o.label} />
            ))}
          </MonoSelect>
        </div>
      </div>

      {/* Column headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1fr) 80px 48px minmax(80px, 200px) 80px",
          gap: "0 var(--frost-line, 16px)",
          padding: "6px 0",
          borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
          fontFamily: "var(--frost-font-mono)",
          fontSize: "10px",
          fontWeight: 800,
          letterSpacing: "1px",
          textTransform: "uppercase",
          color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
        }}
      >
        <div>Repository</div>
        <div>Language</div>
        <div style={{ textAlign: "right" }}>Stars</div>
        <div />
        <div>Status</div>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <BrutalistCard style={{ marginTop: "var(--frost-line, 16px)" }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <BrutalistSkeletonText key={i} paragraph lineCount={2} />
          ))}
        </BrutalistCard>
      )}

      {/* Empty state */}
      {!isLoading && repos.length === 0 && (
        <div
          style={{
            padding: "var(--frost-gap-section, 48px) 0",
            fontFamily: "var(--frost-font-mono)",
            fontSize: "11px",
            fontWeight: 500,
            letterSpacing: "1px",
            textTransform: "uppercase",
            color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: "var(--frost-line, 16px)",
          }}
        >
          <span>
            {isSearchMode ? "No results for this query." : "No repositories yet."}
          </span>
          {!isSearchMode && (
            <BracketButton size="sm" onClick={() => setIngestOpen(true)}>
              Add first repository
            </BracketButton>
          )}
        </div>
      )}

      {/* Virtualized list */}
      {repos.length > 0 && (
        <div
          ref={parentRef}
          style={{ maxHeight: "68vh", overflow: "auto" }}
          aria-label="Repository list"
        >
          <ul
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              position: "relative",
              margin: 0,
              padding: 0,
              listStyle: "none",
            }}
          >
            {rowVirtualizer.getVirtualItems().map((vRow) => {
              const repo = repos[vRow.index];
              if (!repo) return null;
              return (
                <li
                  key={repo.id}
                  ref={rowVirtualizer.measureElement}
                  data-index={vRow.index}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    transform: `translateY(${vRow.start}px)`,
                    listStyle: "none",
                  }}
                >
                  <RepoRow
                    repo={repo}
                    isActive={vRow.index === cursor}
                    onHover={() => setCursor(vRow.index)}
                    onClick={() => navigate(`/repositories/${repo.id}`)}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Fetch-more indicator */}
      {activeQuery.isFetchingNextPage && (
        <div
          style={{
            padding: "8px 0",
            fontFamily: "var(--frost-font-mono)",
            fontSize: "11px",
            letterSpacing: "1px",
            textTransform: "uppercase",
            opacity: 0.5,
          }}
        >
          Loading more…
        </div>
      )}

      <IngestRepositoryDialog open={ingestOpen} onClose={() => setIngestOpen(false)} />

      <style>{`
        @container main (max-width: 768px) {
          .repo-filters {
            flex-direction: column;
            align-items: stretch !important;
          }
        }
      `}</style>
    </main>
  );
}

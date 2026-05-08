import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  BracketButton,
  BracketPagination,
  BracketSearch,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoSelect,
  MonoSelectItem,
  MultiSelect,
  NumberInput,
  SparkLoading,
  StatusBadge,
  Tag,
} from "../../design";
import { useSearchResults, useTrendingTopics } from "../../hooks/useSearch";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { RecommendationsSection } from "./RecommendationsSection";

interface SelectOption {
  id: string;
  text: string;
}

function toggleValue(list: string[], value: string): string[] {
  if (!value || !value.trim()) return list;
  if (list.includes(value)) {
    return list.filter((item) => item !== value);
  }
  return [...list, value];
}

type SearchMode = "auto" | "keyword" | "semantic" | "hybrid";
type ReadState = "all" | "read" | "unread";
type FavoriteState = "all" | "favorited" | "not-favorited";

const SEARCH_MODES: ReadonlySet<SearchMode> = new Set(["auto", "keyword", "semantic", "hybrid"]);
const READ_STATES: ReadonlySet<ReadState> = new Set(["all", "read", "unread"]);
const FAVORITE_STATES: ReadonlySet<FavoriteState> = new Set([
  "all",
  "favorited",
  "not-favorited",
]);

function readEnum<T extends string>(
  raw: string | null,
  allowed: ReadonlySet<T>,
  fallback: T,
): T {
  return raw !== null && (allowed as ReadonlySet<string>).has(raw) ? (raw as T) : fallback;
}

function readList(raw: string | null): string[] {
  if (!raw) return [];
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

function readNumber(raw: string | null, fallback: number): number {
  if (raw === null || raw === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Filter state lives in the URL so back/forward navigation restores it and
  // the URL is shareable. Defaults match the old useState defaults; non-default
  // values round-trip through the query string.
  const query = searchParams.get("q") ?? "";
  const mode = readEnum<SearchMode>(searchParams.get("mode"), SEARCH_MODES, "auto");
  const language = searchParams.get("language") ?? "";
  const readState = readEnum<ReadState>(searchParams.get("readState"), READ_STATES, "all");
  const favoriteState = readEnum<FavoriteState>(
    searchParams.get("favoriteState"),
    FAVORITE_STATES,
    "all",
  );
  const startDate = searchParams.get("startDate") ?? "";
  const endDate = searchParams.get("endDate") ?? "";
  const minSimilarity = Math.max(0, Math.min(1, readNumber(searchParams.get("minSim"), 0.2)));
  const selectedTags = readList(searchParams.get("tags"));
  const selectedDomains = readList(searchParams.get("domains"));
  const page = Math.max(1, Math.floor(readNumber(searchParams.get("page"), 1)));
  const pageSize = Math.max(1, Math.floor(readNumber(searchParams.get("pageSize"), 20)));

  // updateFilters writes a patch to the URL, dropping keys whose value matches
  // the default so the URL stays clean. resetPage clears the page key whenever
  // a filter changes — same setPage(1)-on-filter-change behavior as before.
  function updateFilters(
    patch: Record<string, string | string[] | number | undefined>,
    options?: { resetPage?: boolean },
  ): void {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          const isEmpty =
            value === undefined ||
            value === "" ||
            (Array.isArray(value) && value.length === 0);
          if (isEmpty) {
            next.delete(key);
          } else if (Array.isArray(value)) {
            next.set(key, value.join(","));
          } else {
            next.set(key, String(value));
          }
        }
        if (options?.resetPage) {
          next.delete("page");
        }
        return next;
      },
      { replace: true },
    );
  }

  const semanticMode = mode === "semantic" || mode === "hybrid";

  const trendingQuery = useTrendingTopics(20);

  const searchQuery = useSearchResults(query, {
    limit: pageSize,
    offset: (page - 1) * pageSize,
    mode,
    language: language || undefined,
    startDate: startDate || undefined,
    endDate: endDate || undefined,
    isRead: readState === "all" ? undefined : readState === "read",
    isFavorited: favoriteState === "all" ? undefined : favoriteState === "favorited",
    minSimilarity: semanticMode ? minSimilarity : undefined,
    tags: selectedTags,
    domains: selectedDomains,
  });

  const knownDomains = useMemo(() => {
    const options = new Map<string, SelectOption>();
    for (const facet of searchQuery.data?.facets?.domains ?? []) {
      const value = facet.value.trim();
      if (!value) continue;
      options.set(value, { id: value, text: `${value} (${facet.count})` });
    }
    for (const domain of selectedDomains) {
      if (!options.has(domain)) {
        options.set(domain, { id: domain, text: domain });
      }
    }
    return Array.from(options.values());
  }, [searchQuery.data?.facets?.domains, selectedDomains]);

  const knownTags = useMemo(() => {
    const options = new Map<string, SelectOption>();
    for (const item of trendingQuery.data ?? []) {
      options.set(item.tag, { id: item.tag, text: `${item.tag} (${item.count})` });
    }
    for (const facet of searchQuery.data?.facets?.tags ?? []) {
      const value = facet.value.trim();
      if (!value) continue;
      if (!options.has(value)) {
        options.set(value, { id: value, text: `${value} (${facet.count})` });
      }
    }
    for (const tag of selectedTags) {
      if (!options.has(tag)) {
        options.set(tag, { id: tag, text: tag });
      }
    }
    return Array.from(options.values());
  }, [trendingQuery.data, searchQuery.data?.facets?.tags, selectedTags]);

  const activeFilterCount = [
    mode !== "auto",
    Boolean(language),
    readState !== "all",
    favoriteState !== "all",
    Boolean(startDate),
    Boolean(endDate),
    semanticMode && minSimilarity > 0.2,
    selectedTags.length > 0,
    selectedDomains.length > 0,
  ].filter(Boolean).length;

  const showInitialResultsSkeleton =
    searchQuery.isFetching && !searchQuery.data && query.trim().length > 1;

  function resetFilters(): void {
    updateFilters(
      {
        mode: undefined,
        language: undefined,
        readState: undefined,
        favoriteState: undefined,
        startDate: undefined,
        endDate: undefined,
        minSim: undefined,
        tags: undefined,
        domains: undefined,
      },
      { resetPage: true },
    );
  }

  function clearSearch(): void {
    setSearchParams(new URLSearchParams(), { replace: true });
  }

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
        Search
      </h1>

      <div className="search-sticky-bar">
        <BracketSearch
          id="search-input"
          labelText="Search summaries"
          placeholder="Search by keyword, topic, domain…"
          value={query}
          size="lg"
          onChange={(event) => {
            updateFilters({ q: event.currentTarget.value }, { resetPage: true });
          }}
        />
      </div>

      <BrutalistCard>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "var(--frost-gap-row)",
            marginBottom: "var(--frost-gap-section)",
          }}
        >
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-xs-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: 0,
            }}
          >
            § FILTERS
          </p>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
            <Tag type={activeFilterCount > 0 ? "blue" : "gray"}>
              {activeFilterCount > 0 ? `${activeFilterCount} active` : "No active filters"}
            </Tag>
            <BracketButton kind="ghost" size="sm" onClick={resetFilters}>
              Reset filters
            </BracketButton>
            <BracketButton kind="ghost" size="sm" onClick={clearSearch}>
              Clear all
            </BracketButton>
          </div>
        </div>

        <div
          className="search-filter-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: "var(--frost-gap-row)",
          }}
        >
          <MonoSelect
            id="search-mode"
            labelText="Search mode"
            value={mode}
            onChange={(event) => {
              const next = event.currentTarget.value as SearchMode;
              updateFilters({ mode: next === "auto" ? undefined : next }, { resetPage: true });
            }}
          >
            <MonoSelectItem value="auto" text="Auto" />
            <MonoSelectItem value="keyword" text="Keyword" />
            <MonoSelectItem value="semantic" text="Semantic" />
            <MonoSelectItem value="hybrid" text="Hybrid" />
          </MonoSelect>

          <MonoSelect
            id="search-language"
            labelText="Language"
            value={language}
            onChange={(event) => {
              updateFilters({ language: event.currentTarget.value }, { resetPage: true });
            }}
          >
            <MonoSelectItem value="" text="All languages" />
            <MonoSelectItem value="en" text="English" />
            <MonoSelectItem value="ru" text="Russian" />
            <MonoSelectItem value="auto" text="Auto-detected" />
          </MonoSelect>

          <MonoSelect
            id="search-read-state"
            labelText="Read state"
            value={readState}
            onChange={(event) => {
              const next = event.currentTarget.value as ReadState;
              updateFilters(
                { readState: next === "all" ? undefined : next },
                { resetPage: true },
              );
            }}
          >
            <MonoSelectItem value="all" text="All" />
            <MonoSelectItem value="read" text="Read" />
            <MonoSelectItem value="unread" text="Unread" />
          </MonoSelect>

          <MonoSelect
            id="search-favorite-state"
            labelText="Favorite state"
            value={favoriteState}
            onChange={(event) => {
              const next = event.currentTarget.value as FavoriteState;
              updateFilters(
                { favoriteState: next === "all" ? undefined : next },
                { resetPage: true },
              );
            }}
          >
            <MonoSelectItem value="all" text="All" />
            <MonoSelectItem value="favorited" text="Favorited" />
            <MonoSelectItem value="not-favorited" text="Not favorited" />
          </MonoSelect>

          <MonoSelect
            id="search-start-date"
            labelText="From date"
            value={startDate}
            onChange={(event) => {
              updateFilters({ startDate: event.currentTarget.value }, { resetPage: true });
            }}
          >
            <MonoSelectItem value="" text="Any date" />
          </MonoSelect>

          <MonoSelect
            id="search-end-date"
            labelText="To date"
            value={endDate}
            onChange={(event) => {
              updateFilters({ endDate: event.currentTarget.value }, { resetPage: true });
            }}
          >
            <MonoSelectItem value="" text="Any date" />
          </MonoSelect>

          <NumberInput
            id="search-min-similarity"
            label="Minimum similarity"
            min={0}
            max={1}
            step={0.05}
            value={minSimilarity}
            disabled={!semanticMode}
            onChange={(_, state) => {
              const value = Number(state.value);
              if (Number.isFinite(value)) {
                const clamped = Math.max(0, Math.min(1, value));
                updateFilters(
                  { minSim: clamped === 0.2 ? undefined : clamped },
                  { resetPage: true },
                );
              }
            }}
          />
        </div>
      </BrutalistCard>

      <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
        <MultiSelect
          id="search-tags"
          titleText="Filter by topics"
          label="Choose topics"
          items={knownTags}
          itemToString={(item) => item?.text ?? ""}
          selectedItems={knownTags.filter((tag) => selectedTags.includes(tag.id))}
          onChange={(selection) => {
            const items = (selection.selectedItems ?? []) as SelectOption[];
            updateFilters({ tags: items.map((item) => item.id) }, { resetPage: true });
          }}
        />
        <MultiSelect
          id="search-domains"
          titleText="Filter by domains"
          label="Choose domains"
          items={knownDomains}
          itemToString={(item) => item?.text ?? ""}
          selectedItems={knownDomains.filter((domain) => selectedDomains.includes(domain.id))}
          onChange={(selection) => {
            const items = (selection.selectedItems ?? []) as SelectOption[];
            updateFilters({ domains: items.map((item) => item.id) }, { resetPage: true });
          }}
        />
      </div>

      {searchQuery.data && (
        <BrutalistCard>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-xs-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: "0 0 var(--frost-gap-section) 0",
            }}
          >
            § RESULTS
          </p>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-body-size)",
              color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
              margin: "0 0 var(--frost-gap-section) 0",
            }}
          >
            {searchQuery.data.pagination.total} results · intent {searchQuery.data.intent ?? "unknown"} · mode{" "}
            {searchQuery.data.mode ?? mode}
          </p>

          <div
            className="search-facet-grid"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              gap: "var(--frost-gap-section)",
            }}
          >
            <div>
              <p
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "var(--frost-type-mono-xs-size)",
                  color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                  margin: "0 0 var(--frost-gap-row) 0",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Top domains
              </p>
              <div
                className="tag-row"
                role="group"
                aria-label="Filter by domain"
                style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}
              >
                {(searchQuery.data.facets?.domains ?? []).slice(0, 10).map((facet) => (
                  <BracketButton
                    key={`domain-${facet.value}`}
                    kind="ghost"
                    size="sm"
                    aria-pressed={selectedDomains.includes(facet.value)}
                    style={
                      selectedDomains.includes(facet.value)
                        ? { background: "var(--frost-ink)", color: "var(--frost-page)" }
                        : undefined
                    }
                    onClick={() => {
                      updateFilters(
                        { domains: toggleValue(selectedDomains, facet.value) },
                        { resetPage: true },
                      );
                    }}
                  >
                    {facet.value} ({facet.count})
                  </BracketButton>
                ))}
              </div>
            </div>

            <div>
              <p
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "var(--frost-type-mono-xs-size)",
                  color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                  margin: "0 0 var(--frost-gap-row) 0",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Top tags
              </p>
              <div
                className="tag-row"
                role="group"
                aria-label="Filter by topic tag"
                style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}
              >
                {(searchQuery.data.facets?.tags ?? []).slice(0, 10).map((facet) => (
                  <BracketButton
                    key={`tag-${facet.value}`}
                    kind="ghost"
                    size="sm"
                    aria-pressed={selectedTags.includes(facet.value)}
                    style={
                      selectedTags.includes(facet.value)
                        ? { background: "var(--frost-ink)", color: "var(--frost-page)" }
                        : undefined
                    }
                    onClick={() => {
                      updateFilters(
                        { tags: toggleValue(selectedTags, facet.value) },
                        { resetPage: true },
                      );
                    }}
                  >
                    {facet.value} ({facet.count})
                  </BracketButton>
                ))}
              </div>
            </div>

            <div>
              <p
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "var(--frost-type-mono-xs-size)",
                  color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                  margin: "0 0 var(--frost-gap-row) 0",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                Language mix
              </p>
              <div
                className="tag-row"
                role="group"
                aria-label="Filter by language"
                style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}
              >
                {(searchQuery.data.facets?.languages ?? []).slice(0, 6).map((facet) => (
                  <BracketButton
                    key={`lang-${facet.value}`}
                    kind="ghost"
                    size="sm"
                    aria-pressed={language === facet.value}
                    style={
                      language === facet.value
                        ? { background: "var(--frost-ink)", color: "var(--frost-page)" }
                        : undefined
                    }
                    onClick={() => {
                      updateFilters(
                        { language: language === facet.value ? undefined : facet.value },
                        { resetPage: true },
                      );
                    }}
                  >
                    {facet.value} ({facet.count})
                  </BracketButton>
                ))}
              </div>
            </div>
          </div>
        </BrutalistCard>
      )}

      {!query.trim() && (
        <BrutalistCard>
          <p
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "var(--frost-type-mono-xs-size)",
              fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
              letterSpacing: "var(--frost-type-mono-emph-tracking)",
              textTransform: "uppercase",
              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              margin: "0 0 var(--frost-gap-row) 0",
            }}
          >
            § TRENDING TOPICS
          </p>
          <div
            className="tag-row"
            style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}
          >
            {(trendingQuery.data ?? []).map((topic) => (
              <BracketButton
                key={topic.tag}
                kind="ghost"
                size="sm"
                onClick={() => {
                  updateFilters(
                    { q: topic.tag.replace(/^#/, "") },
                    { resetPage: true },
                  );
                }}
              >
                {topic.tag} ({topic.count})
              </BracketButton>
            ))}
          </div>
        </BrutalistCard>
      )}

      {!query.trim() && <RecommendationsSection />}

      {query.trim().length > 0 && query.trim().length < 2 && (
        <StatusBadge severity="info">
          Enter at least 2 characters — Search API requires 2+ characters for query.
        </StatusBadge>
      )}

      {searchQuery.isFetching && searchQuery.data && (
        <SparkLoading description="Refreshing results…" status="active" />
      )}
      <QueryErrorNotification error={searchQuery.error} title="Search failed" />

      {showInitialResultsSkeleton ? (
        <div
          className="result-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "var(--frost-gap-row)",
          }}
        >
          {Array.from({ length: 3 }).map((_, index) => (
            <BrutalistCard key={`result-skeleton-${index}`}>
              <BrutalistSkeletonText heading width="65%" />
              <BrutalistSkeletonText paragraph lineCount={2} />
              <BrutalistSkeletonText paragraph lineCount={1} width="40%" />
            </BrutalistCard>
          ))}
        </div>
      ) : (
        <div
          className="result-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "var(--frost-gap-row)",
          }}
        >
          {(searchQuery.data?.results ?? []).map((result) => (
            <BrutalistCard key={result.id}>
              <Link
                to={`/library/${result.id}`}
                style={{ textDecoration: "none", color: "inherit", display: "block" }}
              >
                <h3
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                    color: "var(--frost-ink)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  {result.title}
                </h3>
                <div
                  className="tag-row"
                  style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)", marginBottom: "var(--frost-gap-row)" }}
                >
                  <Tag>Score {(result.score * 100).toFixed(0)}%</Tag>
                  <Tag>{result.isRead ? "Read" : "Unread"}</Tag>
                  <Tag type="gray">{result.domain || "Unknown domain"}</Tag>
                </div>
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    color: "var(--frost-ink)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  {result.tldr || result.snippet || "No preview available."}
                </p>
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-xs-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  Added {result.createdAt ? new Date(result.createdAt).toLocaleString() : "Unknown date"}
                </p>
                {result.matchExplanation && (
                  <p
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "var(--frost-type-mono-xs-size)",
                      color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                      margin: "0 0 var(--frost-gap-row) 0",
                    }}
                  >
                    {result.matchExplanation}
                  </p>
                )}
                <div
                  className="tag-row"
                  style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}
                >
                  {result.topicTags.slice(0, 4).map((topic) => (
                    <Tag key={topic}>
                      {topic}
                    </Tag>
                  ))}
                  {(result.matchSignals ?? []).slice(0, 3).map((signal) => (
                    <Tag key={`${result.id}-${signal}`}>
                      {signal}
                    </Tag>
                  ))}
                </div>
              </Link>
            </BrutalistCard>
          ))}
        </div>
      )}

      {searchQuery.data && searchQuery.data.results.length === 0 && (
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
                margin: "0 0 var(--frost-gap-row) 0",
              }}
            >
              No matches found
            </h3>
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "var(--frost-type-mono-body-size)",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                margin: 0,
              }}
            >
              Try broadening filters, switching mode to Hybrid, or lowering similarity.
            </p>
          </div>
          {activeFilterCount > 0 && (
            <div style={{ display: "flex", gap: 16, marginTop: "var(--frost-gap-row)" }}>
              <BracketButton kind="ghost" size="sm" onClick={resetFilters}>
                Clear all filters
              </BracketButton>
            </div>
          )}
        </BrutalistCard>
      )}

      {searchQuery.data && (
        <BracketPagination
          page={page}
          pageSize={pageSize}
          pageSizes={[10, 20, 50, 100]}
          totalItems={searchQuery.data.pagination.total}
          onChange={(event) => {
            updateFilters({
              page: event.page === 1 ? undefined : event.page,
              pageSize: event.pageSize === 20 ? undefined : event.pageSize,
            });
          }}
        />
      )}
    </main>
  );
}

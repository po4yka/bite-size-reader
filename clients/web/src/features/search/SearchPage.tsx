import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"auto" | "keyword" | "semantic" | "hybrid">("auto");
  const [language, setLanguage] = useState("");
  const [readState, setReadState] = useState<"all" | "read" | "unread">("all");
  const [favoriteState, setFavoriteState] = useState<"all" | "favorited" | "not-favorited">("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [minSimilarity, setMinSimilarity] = useState(0.2);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

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
    setMode("auto");
    setLanguage("");
    setReadState("all");
    setFavoriteState("all");
    setStartDate("");
    setEndDate("");
    setMinSimilarity(0.2);
    setSelectedTags([]);
    setSelectedDomains([]);
    setPage(1);
  }

  function clearSearch(): void {
    setQuery("");
    resetFilters();
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

      <BracketSearch
        id="search-input"
        labelText="Search summaries"
        placeholder="Search by keyword, topic, domain…"
        value={query}
        size="lg"
        onChange={(event) => {
          setQuery(event.currentTarget.value);
          setPage(1);
        }}
      />

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
              setMode(event.currentTarget.value as "auto" | "keyword" | "semantic" | "hybrid");
              setPage(1);
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
              setLanguage(event.currentTarget.value);
              setPage(1);
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
              setReadState(event.currentTarget.value as "all" | "read" | "unread");
              setPage(1);
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
              setFavoriteState(event.currentTarget.value as "all" | "favorited" | "not-favorited");
              setPage(1);
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
              setStartDate(event.currentTarget.value);
              setPage(1);
            }}
          >
            <MonoSelectItem value="" text="Any date" />
          </MonoSelect>

          <MonoSelect
            id="search-end-date"
            labelText="To date"
            value={endDate}
            onChange={(event) => {
              setEndDate(event.currentTarget.value);
              setPage(1);
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
                setMinSimilarity(Math.max(0, Math.min(1, value)));
                setPage(1);
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
            setSelectedTags(items.map((item) => item.id));
            setPage(1);
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
            setSelectedDomains(items.map((item) => item.id));
            setPage(1);
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
                      setSelectedDomains((prev) => toggleValue(prev, facet.value));
                      setPage(1);
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
                      setSelectedTags((prev) => toggleValue(prev, facet.value));
                      setPage(1);
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
                      setLanguage((prev) => (prev === facet.value ? "" : facet.value));
                      setPage(1);
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
                  setQuery(topic.tag.replace(/^#/, ""));
                  setPage(1);
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
                  <Tag type="blue">Score {(result.score * 100).toFixed(0)}%</Tag>
                  <Tag type={result.isRead ? "green" : "cool-gray"}>{result.isRead ? "Read" : "Unread"}</Tag>
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
                    <Tag key={topic} type="cyan">
                      {topic}
                    </Tag>
                  ))}
                  {(result.matchSignals ?? []).slice(0, 3).map((signal) => (
                    <Tag key={`${result.id}-${signal}`} type="warm-gray">
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
            setPage(event.page);
            setPageSize(event.pageSize);
          }}
        />
      )}
    </main>
  );
}

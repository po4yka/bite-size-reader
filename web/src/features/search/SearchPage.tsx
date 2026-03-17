import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  InlineLoading,
  InlineNotification,
  MultiSelect,
  NumberInput,
  Pagination,
  Search,
  Select,
  SelectItem,
  SkeletonText,
  Tag,
  TextInput,
  Tile,
} from "@carbon/react";
import { useSearchResults, useTrendingTopics } from "../../hooks/useSearch";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

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
    semanticMode && minSimilarity > 0.2, // 0.2 is the default; > means user changed it
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
    <section className="page-section">
      <h1>Search</h1>
      <Search
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

      <Tile className="search-power-tile">
        <div className="search-power-header">
          <h3>Power filters</h3>
          <div className="form-actions search-power-actions">
            <Tag type={activeFilterCount > 0 ? "blue" : "gray"}>
              {activeFilterCount > 0 ? `${activeFilterCount} active` : "No active filters"}
            </Tag>
            <Button kind="ghost" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
            <Button kind="ghost" size="sm" onClick={clearSearch}>
              Clear all
            </Button>
          </div>
        </div>

        <div className="search-filter-grid">
          <Select
            id="search-mode"
            labelText="Search mode"
            value={mode}
            onChange={(event) => {
              setMode(event.currentTarget.value as "auto" | "keyword" | "semantic" | "hybrid");
              setPage(1);
            }}
          >
            <SelectItem value="auto" text="Auto" />
            <SelectItem value="keyword" text="Keyword" />
            <SelectItem value="semantic" text="Semantic" />
            <SelectItem value="hybrid" text="Hybrid" />
          </Select>

          <Select
            id="search-language"
            labelText="Language"
            value={language}
            onChange={(event) => {
              setLanguage(event.currentTarget.value);
              setPage(1);
            }}
          >
            <SelectItem value="" text="All languages" />
            <SelectItem value="en" text="English" />
            <SelectItem value="ru" text="Russian" />
            <SelectItem value="auto" text="Auto-detected" />
          </Select>

          <Select
            id="search-read-state"
            labelText="Read state"
            value={readState}
            onChange={(event) => {
              setReadState(event.currentTarget.value as "all" | "read" | "unread");
              setPage(1);
            }}
          >
            <SelectItem value="all" text="All" />
            <SelectItem value="read" text="Read" />
            <SelectItem value="unread" text="Unread" />
          </Select>

          <Select
            id="search-favorite-state"
            labelText="Favorite state"
            value={favoriteState}
            onChange={(event) => {
              setFavoriteState(event.currentTarget.value as "all" | "favorited" | "not-favorited");
              setPage(1);
            }}
          >
            <SelectItem value="all" text="All" />
            <SelectItem value="favorited" text="Favorited" />
            <SelectItem value="not-favorited" text="Not favorited" />
          </Select>

          <TextInput
            id="search-start-date"
            labelText="From date"
            type="date"
            value={startDate}
            onChange={(event) => {
              setStartDate(event.currentTarget.value);
              setPage(1);
            }}
          />

          <TextInput
            id="search-end-date"
            labelText="To date"
            type="date"
            value={endDate}
            onChange={(event) => {
              setEndDate(event.currentTarget.value);
              setPage(1);
            }}
          />

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
      </Tile>

      <div className="multiselect-row">
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
        <Tile>
          <div className="search-meta-row">
            <p className="muted">
              {searchQuery.data.pagination.total} results · intent {searchQuery.data.intent ?? "unknown"} · mode{" "}
              {searchQuery.data.mode ?? mode}
            </p>
          </div>

          <div className="search-facet-grid">
            <div>
              <p className="muted">Top domains</p>
              <div className="tag-row">
                {(searchQuery.data.facets?.domains ?? []).slice(0, 10).map((facet) => (
                  <button
                    key={`domain-${facet.value}`}
                    type="button"
                    className="filter-chip"
                    aria-pressed={selectedDomains.includes(facet.value)}
                    onClick={() => {
                      setSelectedDomains((prev) => toggleValue(prev, facet.value));
                      setPage(1);
                    }}
                  >
                    <Tag type={selectedDomains.includes(facet.value) ? "blue" : "gray"}>
                      {facet.value} ({facet.count})
                    </Tag>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="muted">Top tags</p>
              <div className="tag-row">
                {(searchQuery.data.facets?.tags ?? []).slice(0, 10).map((facet) => (
                  <button
                    key={`tag-${facet.value}`}
                    type="button"
                    className="filter-chip"
                    aria-pressed={selectedTags.includes(facet.value)}
                    onClick={() => {
                      setSelectedTags((prev) => toggleValue(prev, facet.value));
                      setPage(1);
                    }}
                  >
                    <Tag type={selectedTags.includes(facet.value) ? "teal" : "gray"}>
                      {facet.value} ({facet.count})
                    </Tag>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="muted">Language mix</p>
              <div className="tag-row">
                {(searchQuery.data.facets?.languages ?? []).slice(0, 6).map((facet) => (
                  <button
                    key={`lang-${facet.value}`}
                    type="button"
                    className="filter-chip"
                    aria-pressed={language === facet.value}
                    onClick={() => {
                      setLanguage((prev) => (prev === facet.value ? "" : facet.value));
                      setPage(1);
                    }}
                  >
                    <Tag type={language === facet.value ? "cyan" : "gray"}>
                      {facet.value} ({facet.count})
                    </Tag>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Tile>
      )}

      {!query.trim() && (
        <Tile>
          <h3>Trending topics</h3>
          <div className="tag-row">
            {(trendingQuery.data ?? []).map((topic) => (
              <button
                key={topic.tag}
                type="button"
                className="filter-chip"
                onClick={() => {
                  setQuery(topic.tag.replace(/^#/, ""));
                  setPage(1);
                }}
              >
                <Tag type="teal">{topic.tag} ({topic.count})</Tag>
              </button>
            ))}
          </div>
        </Tile>
      )}

      {query.trim().length > 0 && query.trim().length < 2 && (
        <InlineNotification
          kind="info"
          title="Enter at least 2 characters"
          subtitle="Search API requires 2+ characters for query."
          hideCloseButton
        />
      )}

      {searchQuery.isFetching && searchQuery.data && <InlineLoading description="Refreshing results…" />}
      <QueryErrorNotification error={searchQuery.error} title="Search failed" />

      {showInitialResultsSkeleton ? (
        <div className="result-grid">
          {Array.from({ length: 3 }).map((_, index) => (
            <Tile key={`result-skeleton-${index}`} className="result-tile">
              <SkeletonText heading width="65%" />
              <SkeletonText paragraph lineCount={2} />
              <SkeletonText paragraph lineCount={1} width="40%" />
            </Tile>
          ))}
        </div>
      ) : (
        <div className="result-grid">
          {(searchQuery.data?.results ?? []).map((result) => (
            <Tile key={result.id} className="result-tile">
              <Link to={`/library/${result.id}`} className="result-tile-link">
                <h3>{result.title}</h3>
                <div className="tag-row">
                  <Tag type="blue">Score {(result.score * 100).toFixed(0)}%</Tag>
                  <Tag type={result.isRead ? "green" : "cool-gray"}>{result.isRead ? "Read" : "Unread"}</Tag>
                  <Tag type="gray">{result.domain || "Unknown domain"}</Tag>
                </div>
                <p>{result.tldr || result.snippet || "No preview available."}</p>
                <p className="muted">
                  Added {result.createdAt ? new Date(result.createdAt).toLocaleString() : "Unknown date"}
                </p>
                {result.matchExplanation && <p className="muted">{result.matchExplanation}</p>}
                <div className="tag-row">
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
            </Tile>
          ))}
        </div>
      )}

      {searchQuery.data && searchQuery.data.results.length === 0 && (
        <Tile>
          <h3>No matches found</h3>
          <p className="muted">Try broadening filters, switching mode to Hybrid, or lowering similarity.</p>
        </Tile>
      )}

      {searchQuery.data && (
        <Pagination
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
    </section>
  );
}

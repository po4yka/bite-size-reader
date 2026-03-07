import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  InlineLoading,
  InlineNotification,
  MultiSelect,
  Pagination,
  Search,
  Tag,
  Tile,
} from "@carbon/react";
import { fetchTrendingTopics, searchSummaries } from "../../api/search";

const PAGE_SIZE = 20;

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [page, setPage] = useState(1);

  const trendingQuery = useQuery({
    queryKey: ["trending-topics"],
    queryFn: () => fetchTrendingTopics(20),
  });

  const searchQuery = useQuery({
    queryKey: ["search", query, selectedTags, selectedDomains, page],
    queryFn: () =>
      searchSummaries(query, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        tags: selectedTags,
        domains: selectedDomains,
      }),
    enabled: query.trim().length > 0,
  });

  const knownDomains = useMemo(() => {
    if (!searchQuery.data) return [];
    const domains = new Set(searchQuery.data.results.map((row) => row.domain).filter(Boolean));
    return Array.from(domains).map((domain) => ({ id: domain, text: domain }));
  }, [searchQuery.data]);

  const knownTags = useMemo(() => {
    const source = trendingQuery.data ?? [];
    return source.map((item) => ({ id: item.tag, text: item.tag }));
  }, [trendingQuery.data]);

  return (
    <section className="page-section">
      <h1>Search</h1>
      <Search
        id="search-input"
        labelText="Search summaries"
        placeholder="Search by keyword, topic, domain"
        value={query}
        size="lg"
        onChange={(event) => {
          setQuery(event.currentTarget.value);
          setPage(1);
        }}
      />

      <div className="multiselect-row">
        <MultiSelect
          id="search-tags"
          titleText="Filter by topics"
          label="Choose topics"
          items={knownTags}
          itemToString={(item) => item?.text ?? ""}
          initialSelectedItems={knownTags.filter((tag) => selectedTags.includes(tag.id))}
          onChange={(selection) => {
            setSelectedTags((selection.selectedItems ?? []).map((item) => item.id));
            setPage(1);
          }}
        />
        <MultiSelect
          id="search-domains"
          titleText="Filter by domains"
          label="Choose domains"
          items={knownDomains}
          itemToString={(item) => item?.text ?? ""}
          initialSelectedItems={knownDomains.filter((domain) => selectedDomains.includes(domain.id))}
          onChange={(selection) => {
            setSelectedDomains((selection.selectedItems ?? []).map((item) => item.id));
            setPage(1);
          }}
        />
      </div>

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
                  setQuery(topic.tag);
                  setPage(1);
                }}
              >
                <Tag type="teal">{topic.tag} ({topic.count})</Tag>
              </button>
            ))}
          </div>
        </Tile>
      )}

      {searchQuery.isFetching && <InlineLoading description="Searching..." />}
      {searchQuery.error && (
        <InlineNotification
          kind="error"
          title="Search failed"
          subtitle={searchQuery.error instanceof Error ? searchQuery.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      <div className="result-grid">
        {(searchQuery.data?.results ?? []).map((result) => (
          <Tile key={result.id} className="result-tile" onClick={() => navigate(`/library/${result.id}`)}>
            <h3>{result.title}</h3>
            <p>{result.tldr || "No TL;DR available."}</p>
            <p className="muted">{result.domain || "Unknown domain"}</p>
            <div className="tag-row">
              {result.topicTags.slice(0, 4).map((topic) => (
                <Tag key={topic} type="cyan">
                  {topic}
                </Tag>
              ))}
            </div>
          </Tile>
        ))}
      </div>

      {searchQuery.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          pageSizes={[10, 20, 50]}
          totalItems={searchQuery.data.pagination.total}
          onChange={(event) => {
            setPage(event.page);
          }}
        />
      )}
    </section>
  );
}

import { useCallback, useEffect, useState } from "react";
import { searchArticles, getTrendingTopics } from "../../api/search";
import { useDebounce } from "../../hooks/useDebounce";
import type { SearchResult, TrendingTopic } from "../../types/api";
import ArticleCard from "../common/ArticleCard";
import LoadingSpinner from "../common/LoadingSpinner";
import LoadingSkeleton from "../common/LoadingSkeleton";
import EmptyState from "../common/EmptyState";
import ErrorBanner from "../common/ErrorBanner";
import TrendingTopics from "./TrendingTopics";

interface SearchPageProps {
  onArticleClick: (id: number) => void;
}

export default function SearchPage({ onArticleClick }: SearchPageProps) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const [trending, setTrending] = useState<TrendingTopic[]>([]);
  const [trendingLoading, setTrendingLoading] = useState(true);

  useEffect(() => {
    getTrendingTopics()
      .then((data) => setTrending(data.topics))
      .catch(() => {
        // Trending topics are non-critical; silently ignore
      })
      .finally(() => setTrendingLoading(false));
  }, []);

  // Reset page when query changes
  useEffect(() => {
    setPage(0);
  }, [debouncedQuery]);

  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (!trimmed) {
      setResults([]);
      setError("");
      setHasMore(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");

    searchArticles(trimmed, { offset: page * 20, limit: 20 })
      .then((data) => {
        if (cancelled) return;
        if (page === 0) {
          setResults(data.results);
        } else {
          setResults((prev) => [...prev, ...data.results]);
        }
        setHasMore(data.pagination.has_more);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Search failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, page]);

  const handleTopicClick = useCallback((tag: string) => {
    setQuery(tag);
  }, []);

  const showTrending = !query.trim();

  return (
    <div className="search-page">
      <input
        type="search"
        className="search-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search articles..."
      />

      {error && <ErrorBanner message={error} />}

      {showTrending && (
        trendingLoading
          ? <LoadingSpinner text="Loading topics..." />
          : trending.length > 0 && (
              <TrendingTopics topics={trending} onTopicClick={handleTopicClick} />
            )
      )}

      {!showTrending && loading && <LoadingSkeleton count={3} />}

      {!showTrending && !loading && !error && results.length === 0 && (
        <EmptyState message="No results found. Try a different query." />
      )}

      {!showTrending && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <ArticleCard
              key={r.id}
              article={{
                ...r,
                summary_250: "",
                estimated_reading_time_min: 0,
                is_read: false,
                is_favorite: false,
                lang: "",
              }}
              onClick={() => onArticleClick(r.id)}
            />
          ))}
          {hasMore && !loading && (
            <button className="btn-primary" onClick={() => setPage((p) => p + 1)}>
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}

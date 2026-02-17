import { useState, useEffect, useRef, useCallback } from "react";
import { fetchSummaries, toggleFavorite } from "../../api/summaries";
import type { SummaryCompact } from "../../types/api";
import ArticleCard from "../common/ArticleCard";
import LoadingSpinner from "../common/LoadingSpinner";
import ErrorBanner from "../common/ErrorBanner";
import EmptyState from "../common/EmptyState";
import FilterBar from "./FilterBar";

const PAGE_SIZE = 20;

interface ArticleListProps {
  onArticleClick: (id: number) => void;
}

export default function ArticleList({ onArticleClick }: ArticleListProps) {
  const [filter, setFilter] = useState<"all" | "unread" | "favorites">("all");
  const [summaries, setSummaries] = useState<SummaryCompact[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const offsetRef = useRef(0);

  const loadPage = useCallback(async (offset: number, replace: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof fetchSummaries>[0] = {
        limit: PAGE_SIZE,
        offset,
        sort: "-created_at",
      };
      if (filter === "unread") params.is_read = false;
      if (filter === "favorites") params.is_favorite = true;

      const res = await fetchSummaries(params);
      setSummaries((prev) => (replace ? res.summaries : [...prev, ...res.summaries]));
      setHasMore(res.pagination.has_more);
      offsetRef.current = offset + res.summaries.length;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load summaries");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  // Reset when filter changes
  useEffect(() => {
    offsetRef.current = 0;
    setSummaries([]);
    setHasMore(true);
    loadPage(0, true);
  }, [loadPage]);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loading) {
          loadPage(offsetRef.current, false);
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loading, loadPage]);

  const handleFavoriteToggle = async (id: number) => {
    try {
      const res = await toggleFavorite(id);
      setSummaries((prev) =>
        prev.map((s) => (s.id === id ? { ...s, is_favorite: res.is_favorite } : s)),
      );
    } catch {
      // Silently fail -- optimistic update not worth the complexity here
    }
  };

  return (
    <div className="article-list">
      <FilterBar filter={filter} onFilterChange={setFilter} />

      {error && <ErrorBanner message={error} onRetry={() => loadPage(0, true)} />}

      {!loading && !error && summaries.length === 0 && (
        <EmptyState message="No articles found" />
      )}

      {summaries.map((article) => (
        <ArticleCard
          key={article.id}
          article={article}
          onClick={() => onArticleClick(article.id)}
          onFavoriteToggle={handleFavoriteToggle}
        />
      ))}

      {loading && <LoadingSpinner />}

      <div ref={sentinelRef} style={{ height: 1 }} />
    </div>
  );
}

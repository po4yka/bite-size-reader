import { useState, useEffect } from "react";
import { fetchSummary, fetchSummaryContent, markAsRead, toggleFavorite } from "../../api/summaries";
import type { SummaryDetail, SummaryContent } from "../../types/api";
import LoadingSpinner from "../common/LoadingSpinner";
import ErrorBanner from "../common/ErrorBanner";
import ArticleContent from "./ArticleContent";

interface ArticleDetailProps {
  articleId: number;
  onBack: () => void;
}

export default function ArticleDetail({ articleId, onBack }: ArticleDetailProps) {
  const [detail, setDetail] = useState<SummaryDetail | null>(null);
  const [content, setContent] = useState<SummaryContent | null>(null);
  const [showContent, setShowContent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchSummary(articleId)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load article"))
      .finally(() => setLoading(false));
  }, [articleId]);

  const handleToggleContent = async () => {
    if (!showContent && !content) {
      try {
        const res = await fetchSummaryContent(articleId);
        setContent(res);
      } catch {
        // Content may not be available for all summaries
      }
    }
    setShowContent((prev) => !prev);
  };

  const handleMarkAsRead = async () => {
    if (!detail) return;
    try {
      await markAsRead(articleId);
      setDetail({ ...detail, is_read: true });
    } catch {
      // Silently fail
    }
  };

  const handleToggleFavorite = async () => {
    if (!detail) return;
    try {
      const res = await toggleFavorite(articleId);
      setDetail({ ...detail, is_favorite: res.is_favorite });
    } catch {
      // Silently fail
    }
  };

  if (loading) return <LoadingSpinner text="Loading article..." />;
  if (error) return <ErrorBanner message={error} onRetry={onBack} />;
  if (!detail) return null;

  const domain = detail.domain || new URL(detail.url).hostname;

  return (
    <div className="article-detail">
      <button className="btn-back" onClick={onBack}>Back</button>

      <h1 className="article-detail-title">{detail.title || "Untitled"}</h1>

      <div className="article-detail-meta">
        <span>{domain}</span>
        <span>{detail.estimated_reading_time_min} min read</span>
        {detail.lang && <span>{detail.lang.toUpperCase()}</span>}
      </div>

      <div className="article-detail-actions">
        {!detail.is_read && (
          <button className="btn-primary" onClick={handleMarkAsRead}>
            Mark as read
          </button>
        )}
        <button className="btn-primary" onClick={handleToggleFavorite}>
          {detail.is_favorite ? "Unfavorite" : "Favorite"}
        </button>
        <button
          className="btn-primary"
          onClick={() => window.open(detail.url, "_blank", "noopener,noreferrer")}
        >
          Open original
        </button>
      </div>

      <section className="article-detail-section">
        <h2>Summary</h2>
        <p>{detail.summary_250}</p>
      </section>

      {detail.summary_1000 && (
        <section className="article-detail-section">
          <h2>Detailed summary</h2>
          <p>{detail.summary_1000}</p>
        </section>
      )}

      {detail.key_ideas && detail.key_ideas.length > 0 && (
        <section className="article-detail-section">
          <h2>Key ideas</h2>
          <ul>
            {detail.key_ideas.map((ki, i) => (
              <li key={i}>
                {ki.idea}
                {ki.relevance && <span className="relevance"> -- {ki.relevance}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {detail.entities && detail.entities.length > 0 && (
        <section className="article-detail-section">
          <h2>Entities</h2>
          <div className="article-card-tags">
            {detail.entities.map((e, i) => (
              <span key={i} className="tag" title={e.context}>
                {e.name} ({e.type})
              </span>
            ))}
          </div>
        </section>
      )}

      {detail.topic_tags && detail.topic_tags.length > 0 && (
        <section className="article-detail-section">
          <h2>Topics</h2>
          <div className="article-card-tags">
            {detail.topic_tags.map((tag) => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        </section>
      )}

      <section className="article-detail-section">
        <button className="btn-primary" onClick={handleToggleContent}>
          {showContent ? "Hide full content" : "Show full content"}
        </button>
        {showContent && content?.markdown && (
          <ArticleContent markdown={content.markdown} />
        )}
        {showContent && !content?.markdown && (
          <p className="text-muted">Full content not available.</p>
        )}
      </section>
    </div>
  );
}

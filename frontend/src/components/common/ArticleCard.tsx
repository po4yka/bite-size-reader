import type { SummaryCompact } from "../../types/api";

interface ArticleCardProps {
  article: SummaryCompact;
  onClick: () => void;
  onFavoriteToggle?: (id: number) => void;
}

export default function ArticleCard({ article, onClick, onFavoriteToggle }: ArticleCardProps) {
  const domain = article.domain || new URL(article.url).hostname;

  return (
    <div className="article-card" onClick={onClick}>
      <div className="article-card-header">
        <span className="article-card-title">{article.title || "Untitled"}</span>
        {onFavoriteToggle && (
          <button
            className="article-card-fav"
            onClick={(e) => {
              e.stopPropagation();
              onFavoriteToggle(article.id);
            }}
          >
            {article.is_favorite ? "\u2605" : "\u2606"}
          </button>
        )}
      </div>
      <div className="article-card-meta">
        <span>{domain}</span>
        <span>{article.estimated_reading_time_min} min</span>
        {article.is_read && <span>Read</span>}
      </div>
      {article.tldr && <div className="article-card-tldr">{article.tldr}</div>}
      {article.topic_tags && article.topic_tags.length > 0 && (
        <div className="article-card-tags">
          {article.topic_tags.slice(0, 4).map((tag) => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

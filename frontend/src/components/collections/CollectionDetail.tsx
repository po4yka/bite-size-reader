import { useCallback, useEffect, useState } from "react";
import { fetchCollectionItems, removeFromCollection } from "../../api/collections";
import type { CollectionItem } from "../../types/api";
import ArticleCard from "../common/ArticleCard";
import LoadingSpinner from "../common/LoadingSpinner";
import ErrorBanner from "../common/ErrorBanner";
import EmptyState from "../common/EmptyState";

interface CollectionDetailProps {
  collectionId: number;
  onArticleClick: (id: number) => void;
  onBack: () => void;
}

export default function CollectionDetail({
  collectionId,
  onArticleClick,
  onBack,
}: CollectionDetailProps) {
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      setLoading(true);
      const result = await fetchCollectionItems(collectionId);
      setItems(result.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load collection items");
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRemove = async (itemId: number) => {
    const confirmed = await new Promise<boolean>((resolve) => {
      const wa = window.Telegram?.WebApp;
      if (wa?.showConfirm) {
        wa.showConfirm("Remove this item from the collection?", resolve);
      } else {
        resolve(window.confirm("Remove this item from the collection?"));
      }
    });
    if (!confirmed) return;

    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("heavy");
    try {
      await removeFromCollection(collectionId, itemId);
      setItems((prev) => prev.filter((item) => item.id !== itemId));
    } catch (e) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("error");
      setError(e instanceof Error ? e.message : "Failed to remove item");
    }
  };

  return (
    <div className="collection-detail">
      <button className="btn-back" onClick={onBack}>
        Back
      </button>

      {loading && <LoadingSpinner text="Loading items..." />}
      {error && <ErrorBanner message={error} onRetry={load} />}

      {!loading && !error && items.length === 0 && (
        <EmptyState message="This collection is empty." />
      )}

      {!loading && items.length > 0 && (
        <div className="collection-items">
          {items.map((item) => (
            <div key={item.id} className="collection-item-wrapper">
              <ArticleCard
                article={{
                  id: item.summary_id,
                  request_id: "",
                  title: item.title,
                  url: item.url,
                  domain: item.domain,
                  tldr: item.tldr,
                  summary_250: "",
                  topic_tags: item.topic_tags,
                  estimated_reading_time_min: 0,
                  is_read: false,
                  is_favorite: false,
                  lang: "",
                  created_at: item.added_at,
                }}
                onClick={() => onArticleClick(item.summary_id)}
              />
              <button
                className="btn-remove-item"
                onClick={() => handleRemove(item.id)}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

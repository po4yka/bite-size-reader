import { useCallback, useEffect, useState } from "react";
import { fetchCollections, createCollection } from "../../api/collections";
import type { Collection } from "../../types/api";
import LoadingSkeleton from "../common/LoadingSkeleton";
import ErrorBanner from "../common/ErrorBanner";
import EmptyState from "../common/EmptyState";

interface CollectionTreeProps {
  onCollectionClick: (id: number) => void;
}

export default function CollectionTree({ onCollectionClick }: CollectionTreeProps) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setError("");
      const result = await fetchCollections();
      setCollections(result.collections);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load collections");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    try {
      await createCollection(name.trim());
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success");
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create collection");
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <LoadingSkeleton count={3} type="collection" />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;

  return (
    <div className="collection-tree">
      <form className="collection-create-form" onSubmit={handleCreate}>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New collection name"
          disabled={creating}
        />
        <button type="submit" disabled={creating || !name.trim()}>
          {creating ? "..." : "Create"}
        </button>
      </form>

      {collections.length === 0 ? (
        <EmptyState message="No collections yet. Create one above." />
      ) : (
        <ul className="collection-list">
          {collections.map((col) => (
            <li key={col.id} className="collection-list-item">
              <button
                className="collection-item-btn"
                onClick={() => onCollectionClick(col.id)}
              >
                <span className="collection-item-name">{col.name}</span>
                <span className="collection-item-count">
                  {col.item_count} {col.item_count === 1 ? "item" : "items"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { fetchCollections, addToCollection } from "../../api/collections";
import type { Collection } from "../../types/api";
import LoadingSpinner from "../common/LoadingSpinner";
import ErrorBanner from "../common/ErrorBanner";

interface AddToCollectionSheetProps {
  summaryId: number;
  onClose: () => void;
}

export default function AddToCollectionSheet({
  summaryId,
  onClose,
}: AddToCollectionSheetProps) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addedIds, setAddedIds] = useState<Set<number>>(new Set());

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

  const handleToggle = async (collectionId: number) => {
    if (addedIds.has(collectionId)) return;
    try {
      await addToCollection(collectionId, summaryId);
      setAddedIds((prev) => new Set(prev).add(collectionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add to collection");
    }
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="sheet-overlay" onClick={handleOverlayClick}>
      <div className="sheet-content">
        <div className="sheet-header">
          <span className="sheet-title">Add to Collection</span>
          <button className="sheet-close" onClick={onClose}>
            Close
          </button>
        </div>

        {loading && <LoadingSpinner text="Loading collections..." />}
        {error && <ErrorBanner message={error} />}

        {!loading && collections.length === 0 && (
          <p className="empty">No collections available. Create one first.</p>
        )}

        {!loading && collections.length > 0 && (
          <ul className="sheet-collection-list">
            {collections.map((col) => (
              <li key={col.id} className="sheet-collection-item">
                <label className="sheet-collection-label">
                  <input
                    type="checkbox"
                    checked={addedIds.has(col.id)}
                    onChange={() => handleToggle(col.id)}
                    disabled={addedIds.has(col.id)}
                  />
                  <span className="sheet-collection-name">{col.name}</span>
                  <span className="sheet-collection-count">
                    {col.item_count} {col.item_count === 1 ? "item" : "items"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

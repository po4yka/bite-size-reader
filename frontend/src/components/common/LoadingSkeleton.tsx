interface LoadingSkeletonProps {
  count?: number;
  type?: "card" | "collection" | "search";
}

function SkeletonCard() {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <div className="skeleton skeleton-pulse skeleton-title" />
      <div className="skeleton skeleton-pulse skeleton-meta" />
      <div className="skeleton skeleton-pulse skeleton-body" />
      <div className="skeleton-tags">
        <div className="skeleton skeleton-pulse skeleton-tag" />
        <div className="skeleton skeleton-pulse skeleton-tag" />
        <div className="skeleton skeleton-pulse skeleton-tag" />
      </div>
    </div>
  );
}

function SkeletonCollection() {
  return (
    <div className="skeleton-collection" aria-hidden="true">
      <div className="skeleton skeleton-pulse skeleton-collection-name" />
      <div className="skeleton skeleton-pulse skeleton-collection-count" />
    </div>
  );
}

export default function LoadingSkeleton({ count = 4, type = "card" }: LoadingSkeletonProps) {
  const Skeleton = type === "collection" ? SkeletonCollection : SkeletonCard;
  return (
    <div className="skeleton-container" role="status" aria-label="Loading content">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} />
      ))}
    </div>
  );
}

interface FilterBarProps {
  filter: "all" | "unread" | "favorites";
  onFilterChange: (f: "all" | "unread" | "favorites") => void;
}

const FILTERS: Array<{ key: "all" | "unread" | "favorites"; label: string }> = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "favorites", label: "Favorites" },
];

export default function FilterBar({ filter, onFilterChange }: FilterBarProps) {
  const handleClick = (key: "all" | "unread" | "favorites") => {
    if (key !== filter) {
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    }
    onFilterChange(key);
  };

  return (
    <div className="filter-bar" role="tablist" aria-label="Article filter">
      {FILTERS.map((f) => (
        <button
          key={f.key}
          className={`tag-btn${filter === f.key ? " active" : ""}`}
          onClick={() => handleClick(f.key)}
          role="tab"
          aria-selected={filter === f.key}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}

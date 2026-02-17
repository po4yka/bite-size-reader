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
  return (
    <div className="filter-bar">
      {FILTERS.map((f) => (
        <button
          key={f.key}
          className={`tag-btn${filter === f.key ? " active" : ""}`}
          onClick={() => onFilterChange(f.key)}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}

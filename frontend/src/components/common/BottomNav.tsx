import type { Route } from "../../hooks/useRouter";

interface BottomNavProps {
  activePage: Route["page"];
  onNavigate: (route: Route) => void;
}

const NAV_ITEMS: Array<{ page: Route["page"]; label: string; icon: string }> = [
  { page: "library", label: "Library", icon: "\u{1F4DA}" },
  { page: "search", label: "Search", icon: "\u{1F50D}" },
  { page: "submit", label: "Submit", icon: "\u{2795}" },
  { page: "collections", label: "Collections", icon: "\u{1F4C1}" },
  { page: "more", label: "More", icon: "\u{2699}\uFE0F" },
];

export default function BottomNav({ activePage, onNavigate }: BottomNavProps) {
  return (
    <nav className="bottom-nav">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.page}
          className={`bottom-nav-item${activePage === item.page ? " active" : ""}`}
          onClick={() => onNavigate({ page: item.page })}
        >
          <span className="bottom-nav-icon">{item.icon}</span>
          <span className="bottom-nav-label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

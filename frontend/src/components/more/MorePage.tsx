import { useState } from "react";
import type { Route } from "../../hooks/useRouter";
import ChannelList from "../ChannelList";
import PreferencesForm from "../PreferencesForm";
import DigestHistory from "../DigestHistory";
import UserStatsView from "./UserStats";
import AdminPage from "./admin/AdminPage";

interface MorePageProps {
  sub?: "digest" | "profile" | "stats" | "preferences" | "admin";
  canAccessAdmin?: boolean;
  onNavigate: (route: Route) => void;
}

type DigestTab = "channels" | "preferences" | "history";

function DigestSection() {
  const [tab, setTab] = useState<DigestTab>("channels");

  return (
    <div className="digest-section">
      <div className="digest-tabs">
        <button
          className={`digest-tab ${tab === "channels" ? "active" : ""}`}
          onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged(); setTab("channels"); }}
        >
          Channels
        </button>
        <button
          className={`digest-tab ${tab === "preferences" ? "active" : ""}`}
          onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged(); setTab("preferences"); }}
        >
          Settings
        </button>
        <button
          className={`digest-tab ${tab === "history" ? "active" : ""}`}
          onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged(); setTab("history"); }}
        >
          History
        </button>
      </div>

      <div className="digest-tab-content">
        {tab === "channels" && <ChannelList />}
        {tab === "preferences" && <PreferencesForm />}
        {tab === "history" && <DigestHistory />}
      </div>
    </div>
  );
}

type MoreSub = "digest" | "stats" | "preferences" | "admin";

export default function MorePage({ sub, canAccessAdmin = false, onNavigate }: MorePageProps) {
  const menuItems: Array<{ label: string; sub: MoreSub }> = [
    { label: "Digest Management", sub: "digest" },
    { label: "Reading Stats", sub: "stats" },
    { label: "Preferences", sub: "preferences" },
    ...(canAccessAdmin ? ([{ label: "Admin Tools", sub: "admin" }] as const) : []),
  ];

  if (sub === "digest") return <DigestSection />;
  if (sub === "stats") return <UserStatsView />;
  if (sub === "preferences") return <PreferencesForm />;
  if (sub === "admin") {
    if (!canAccessAdmin) {
      return <div className="error">Access denied.</div>;
    }
    return <AdminPage />;
  }

  return (
    <div className="more-page">
      <ul className="more-menu">
        {menuItems.map((item) => (
          <li key={item.sub}>
            <button
              className="more-menu-item"
              onClick={() => {
                window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("light");
                onNavigate({ page: "more", sub: item.sub });
              }}
            >
              <span>{item.label}</span>
              <span className="more-menu-arrow">&rsaquo;</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

import { useState } from "react";
import { useTelegram } from "./hooks/useTelegram";
import ChannelList from "./components/ChannelList";
import PreferencesForm from "./components/PreferencesForm";
import DigestHistory from "./components/DigestHistory";

type Tab = "channels" | "preferences" | "history";

export default function App() {
  const { user } = useTelegram();
  const [activeTab, setActiveTab] = useState<Tab>("channels");

  if (!user) {
    return <div className="loading">Connecting to Telegram...</div>;
  }

  return (
    <div className="app">
      <nav className="tabs">
        <button
          className={activeTab === "channels" ? "active" : ""}
          onClick={() => setActiveTab("channels")}
        >
          Channels
        </button>
        <button
          className={activeTab === "preferences" ? "active" : ""}
          onClick={() => setActiveTab("preferences")}
        >
          Preferences
        </button>
        <button
          className={activeTab === "history" ? "active" : ""}
          onClick={() => setActiveTab("history")}
        >
          History
        </button>
      </nav>

      <main className="content">
        {activeTab === "channels" && <ChannelList />}
        {activeTab === "preferences" && <PreferencesForm />}
        {activeTab === "history" && <DigestHistory />}
      </main>
    </div>
  );
}

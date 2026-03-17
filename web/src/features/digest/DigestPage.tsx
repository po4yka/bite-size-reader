import { useState } from "react";
import { Tab, TabList, TabPanel, TabPanels, Tabs } from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";
import { ChannelsTab } from "./ChannelsTab";
import { DigestUnavailableNotice } from "./DigestUnavailableNotice";
import { HistoryTab } from "./HistoryTab";
import { PreferencesTab } from "./PreferencesTab";

export default function DigestPage() {
  const { mode, user } = useAuth();
  const [selectedTabIndex, setSelectedTabIndex] = useState(0);

  return (
    <section className="page-section">
      <h1>Digest</h1>

      {mode !== "telegram-webapp" && <DigestUnavailableNotice />}

      {mode === "telegram-webapp" && (
        <Tabs selectedIndex={selectedTabIndex} onChange={({ selectedIndex }) => setSelectedTabIndex(selectedIndex)}>
          <TabList aria-label="Digest tabs" contained>
            <Tab>Channels</Tab>
            <Tab>Preferences</Tab>
            <Tab>History</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>
              <ChannelsTab isOwner={Boolean(user?.isOwner)} isActive={selectedTabIndex === 0} />
            </TabPanel>
            <TabPanel>
              <PreferencesTab />
            </TabPanel>
            <TabPanel>
              <HistoryTab />
            </TabPanel>
          </TabPanels>
        </Tabs>
      )}
    </section>
  );
}

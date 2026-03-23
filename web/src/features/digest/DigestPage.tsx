import { useState } from "react";
import { Tab, TabList, TabPanel, TabPanels, Tabs } from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";
import { ChannelsTab } from "./ChannelsTab";
import { CustomDigestTab } from "./CustomDigestTab";
import { DigestUnavailableNotice } from "./DigestUnavailableNotice";
import { HistoryTab } from "./HistoryTab";
import { PreferencesTab } from "./PreferencesTab";
import { RSSFeedsTab } from "./RSSFeedsTab";

export default function DigestPage() {
  const { mode, user } = useAuth();
  const [selectedTabIndex, setSelectedTabIndex] = useState(0);

  const isTelegramMode = mode === "telegram-webapp";

  return (
    <section className="page-section">
      <h1>Digest</h1>

      {isTelegramMode ? (
        <Tabs selectedIndex={selectedTabIndex} onChange={({ selectedIndex }) => setSelectedTabIndex(selectedIndex)}>
          <TabList aria-label="Digest tabs" contained>
            <Tab>Channels</Tab>
            <Tab>RSS Feeds</Tab>
            <Tab>Preferences</Tab>
            <Tab>History</Tab>
            <Tab>Custom Digests</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>
              <ChannelsTab isOwner={Boolean(user?.isOwner)} isActive={selectedTabIndex === 0} />
            </TabPanel>
            <TabPanel>
              <RSSFeedsTab />
            </TabPanel>
            <TabPanel>
              <PreferencesTab />
            </TabPanel>
            <TabPanel>
              <HistoryTab />
            </TabPanel>
            <TabPanel>
              <CustomDigestTab />
            </TabPanel>
          </TabPanels>
        </Tabs>
      ) : (
        <>
          <DigestUnavailableNotice />
          <RSSFeedsTab />
        </>
      )}
    </section>
  );
}

import { useState } from "react";
import { BracketTab, BracketTabList, BracketTabPanel, BracketTabPanels, BracketTabs } from "../../design";
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
    <section
      className="page-section"
      style={{
        maxWidth: "var(--frost-strip-7, 1232px)",
        padding: "var(--frost-pad-page, 32px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section, 48px)",
      }}
    >
      <h1>Digest</h1>

      {isTelegramMode ? (
        <BracketTabs selectedIndex={selectedTabIndex} onChange={({ selectedIndex }) => setSelectedTabIndex(selectedIndex)}>
          <BracketTabList aria-label="Digest tabs" contained>
            <BracketTab>Channels</BracketTab>
            <BracketTab>RSS Feeds</BracketTab>
            <BracketTab>Preferences</BracketTab>
            <BracketTab>History</BracketTab>
            <BracketTab>Custom Digests</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>
              <ChannelsTab isOwner={Boolean(user?.isOwner)} isActive={selectedTabIndex === 0} />
            </BracketTabPanel>
            <BracketTabPanel>
              <RSSFeedsTab />
            </BracketTabPanel>
            <BracketTabPanel>
              <PreferencesTab />
            </BracketTabPanel>
            <BracketTabPanel>
              <HistoryTab />
            </BracketTabPanel>
            <BracketTabPanel>
              <CustomDigestTab />
            </BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      ) : (
        <>
          <DigestUnavailableNotice />
          <RSSFeedsTab />
        </>
      )}
    </section>
  );
}

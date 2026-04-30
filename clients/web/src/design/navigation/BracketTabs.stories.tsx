import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  BracketTabs,
  BracketTabList,
  BracketTab,
  BracketTabPanels,
  BracketTabPanel,
} from "./BracketTabs";

const meta = {
  title: "Navigation/BracketTabs",
  component: BracketTabs,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof BracketTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <BracketTabs defaultSelectedIndex={0}>
      <BracketTabList aria-label="Primary tabs">
        <BracketTab>Overview</BracketTab>
        <BracketTab>Activity</BracketTab>
        <BracketTab>Settings</BracketTab>
      </BracketTabList>
      <BracketTabPanels>
        <BracketTabPanel>
          <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>Overview panel content.</p>
        </BracketTabPanel>
        <BracketTabPanel>
          <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>Activity panel content.</p>
        </BracketTabPanel>
        <BracketTabPanel>
          <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>Settings panel content.</p>
        </BracketTabPanel>
      </BracketTabPanels>
    </BracketTabs>
  ),
};

export const Controlled: Story = {
  render: () => {
    const [idx, setIdx] = useState(1);
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1 }}>
          Controlled — active: {idx}
        </p>
        <BracketTabs
          selectedIndex={idx}
          onChange={({ selectedIndex }) => setIdx(selectedIndex)}
        >
          <BracketTabList aria-label="Controlled tabs">
            <BracketTab>Articles</BracketTab>
            <BracketTab>Collections</BracketTab>
            <BracketTab>Tags</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>Articles panel.</BracketTabPanel>
            <BracketTabPanel>Collections panel.</BracketTabPanel>
            <BracketTabPanel>Tags panel.</BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      </div>
    );
  },
};

export const WithDisabled: Story = {
  render: () => (
    <BracketTabs defaultSelectedIndex={0}>
      <BracketTabList aria-label="Tabs with disabled">
        <BracketTab>Enabled</BracketTab>
        <BracketTab disabled>Disabled</BracketTab>
        <BracketTab>Also Enabled</BracketTab>
      </BracketTabList>
      <BracketTabPanels>
        <BracketTabPanel>First panel.</BracketTabPanel>
        <BracketTabPanel>This panel is unreachable (tab disabled).</BracketTabPanel>
        <BracketTabPanel>Third panel.</BracketTabPanel>
      </BracketTabPanels>
    </BracketTabs>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 48 }}>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>
          Default (first tab active — spark indicator)
        </p>
        <BracketTabs defaultSelectedIndex={0}>
          <BracketTabList aria-label="Default variant">
            <BracketTab>Library</BracketTab>
            <BracketTab>Search</BracketTab>
            <BracketTab>Digest</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>Library content.</BracketTabPanel>
            <BracketTabPanel>Search content.</BracketTabPanel>
            <BracketTabPanel>Digest content.</BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      </div>

      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>
          Second tab active
        </p>
        <BracketTabs defaultSelectedIndex={1}>
          <BracketTabList aria-label="Second active">
            <BracketTab>Webhooks</BracketTab>
            <BracketTab>Rules</BracketTab>
            <BracketTab>Signals</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>Webhooks content.</BracketTabPanel>
            <BracketTabPanel>Rules content.</BracketTabPanel>
            <BracketTabPanel>Signals content.</BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      </div>

      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>
          With disabled tab
        </p>
        <BracketTabs defaultSelectedIndex={0}>
          <BracketTabList aria-label="With disabled">
            <BracketTab>Active</BracketTab>
            <BracketTab disabled>Unavailable</BracketTab>
            <BracketTab>Other</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>Active panel.</BracketTabPanel>
            <BracketTabPanel>N/A</BracketTabPanel>
            <BracketTabPanel>Other panel.</BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      </div>
    </div>
  ),
};

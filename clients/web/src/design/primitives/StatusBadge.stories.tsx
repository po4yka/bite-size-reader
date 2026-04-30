import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusBadge } from "./StatusBadge";

const meta = {
  title: "Frost/StatusBadge",
  component: StatusBadge,
  parameters: { layout: "padded" },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    severity: "info",
    title: "Processing",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "flex-start" }}>
      <StatusBadge severity="info" title="OK">
      </StatusBadge>

      <StatusBadge severity="info" title="Fetching" subtitle="Retrieving feed data">
      </StatusBadge>

      <StatusBadge severity="warn" title="Paused" subtitle="Action required">
      </StatusBadge>

      <StatusBadge severity="alarm" title="Failed" subtitle="Connection refused">
      </StatusBadge>

      <StatusBadge severity="info" title="Sync complete" dismissible onDismiss={() => undefined}>
      </StatusBadge>

      <StatusBadge severity="alarm" title="Import failed" subtitle="Check source URL" dismissible onDismiss={() => undefined}>
      </StatusBadge>

      <StatusBadge severity="info" title="Ready" subtitle="Brief prepared" caption="4 articles · 2025-04-30">
      </StatusBadge>
    </div>
  ),
};

export const Severities: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>
        Info — mono body weight, no prefix glyph, no spark
      </div>
      <StatusBadge severity="info" title="info severity" />

      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginTop: 8, marginBottom: 4 }}>
        Warn — mono extrabold, ! prefix glyph, no spark
      </div>
      <StatusBadge severity="warn" title="warn severity" />

      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginTop: 8, marginBottom: 4 }}>
        Alarm — mono extrabold, 2px leading spark hairline, text stays ink (never red)
      </div>
      <StatusBadge severity="alarm" title="alarm severity" />
    </div>
  ),
};

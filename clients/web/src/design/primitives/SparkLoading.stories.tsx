import type { Meta, StoryObj } from "@storybook/react-vite";
import { SparkLoading } from "./SparkLoading";

const meta = {
  title: "Frost/SparkLoading",
  component: SparkLoading,
  parameters: { layout: "padded" },
} satisfies Meta<typeof SparkLoading>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    status: "active",
    description: "Fetching",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "flex-start" }}>
      <SparkLoading status="inactive" description="Inactive" />
      <SparkLoading status="active" description="Fetching" />
      <SparkLoading status="finished" description="Complete" />
      <SparkLoading status="error" description="Failed" />
      <SparkLoading status="active" description="Processing feed" />
      <SparkLoading status="active" />
    </div>
  ),
};

export const StatusStates: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "flex-start" }}>
      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>
        Inactive — static dot, label alpha 0.55
      </div>
      <SparkLoading status="inactive" description="Idle" />

      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginTop: 8, marginBottom: 4 }}>
        Active — frost-blinker animated dot, label alpha 1.0
      </div>
      <SparkLoading status="active" description="Syncing" />

      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginTop: 8, marginBottom: 4 }}>
        Finished — static ✓ glyph, label alpha 1.0
      </div>
      <SparkLoading status="finished" description="Done" />

      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginTop: 8, marginBottom: 4 }}>
        Error — static ! glyph, 2px leading spark hairline
      </div>
      <SparkLoading status="error" description="Connection refused" />
    </div>
  ),
};

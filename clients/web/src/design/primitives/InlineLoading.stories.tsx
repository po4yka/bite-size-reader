import type { Meta, StoryObj } from "@storybook/react-vite";
import { InlineLoading } from "./InlineLoading";

const meta = {
  title: "Primitives/InlineLoading",
  component: InlineLoading,
  parameters: { layout: "padded" },
} satisfies Meta<typeof InlineLoading>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    status: "active",
    description: "Loading…",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <InlineLoading status="active" description="Loading data…" />
      <InlineLoading status="inactive" description="Idle" />
      <InlineLoading status="finished" description="Done" />
      <InlineLoading status="error" description="Failed to load" />
      <InlineLoading status="active" />
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import { ProgressBar } from "./ProgressBar";

const meta = {
  title: "Primitives/ProgressBar",
  component: ProgressBar,
  parameters: { layout: "padded" },
} satisfies Meta<typeof ProgressBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    label: "Processing",
    value: 45,
    max: 100,
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <ProgressBar label="Active — 45%" value={45} status="active" />
      <ProgressBar label="Finished — 100%" value={100} status="finished" />
      <ProgressBar label="Error — 60%" value={60} status="error" />
      <ProgressBar label="Indeterminate" />
      <ProgressBar label="Small size" value={70} size="small" />
      <ProgressBar label="Big size" value={70} size="big" />
      <ProgressBar label="With helper" value={30} helperText="30 of 100 items processed" />
      <ProgressBar value={80} hideLabel label="Hidden label" />
    </div>
  ),
};

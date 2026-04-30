import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tag } from "./Tag";

const meta = {
  title: "Primitives/Tag",
  component: Tag,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof Tag>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: "Technology",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <Tag>Default</Tag>
        <Tag type="red">Critical</Tag>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Tag filter onClose={() => {}}>Filterable</Tag>
        <Tag disabled>Disabled</Tag>
        <Tag type="red" disabled>Critical Disabled</Tag>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Tag type="blue">Blue (deprecated → default)</Tag>
        <Tag type="green">Green (deprecated → default)</Tag>
        <Tag type="gray">Gray</Tag>
      </div>
    </div>
  ),
};

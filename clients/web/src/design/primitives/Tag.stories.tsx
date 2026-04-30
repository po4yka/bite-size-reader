import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tag } from "./Tag";

const meta = {
  title: "Primitives/Tag",
  component: Tag,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Tag>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: "Technology",
    type: "blue",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <Tag type="gray">Gray</Tag>
        <Tag type="blue">Blue</Tag>
        <Tag type="cyan">Cyan</Tag>
        <Tag type="teal">Teal</Tag>
        <Tag type="green">Green</Tag>
        <Tag type="red">Red</Tag>
        <Tag type="magenta">Magenta</Tag>
        <Tag type="purple">Purple</Tag>
        <Tag type="warm-gray">Warm Gray</Tag>
        <Tag type="cool-gray">Cool Gray</Tag>
        <Tag type="high-contrast">High Contrast</Tag>
        <Tag type="outline">Outline</Tag>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Tag type="blue" size="sm">Small</Tag>
        <Tag type="blue" size="md">Medium</Tag>
        <Tag type="blue" size="lg">Large</Tag>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Tag type="blue" filter onClose={() => {}}>Filterable</Tag>
        <Tag type="blue" disabled>Disabled</Tag>
      </div>
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import { IconButton } from "./IconButton";
import { Close, Edit, TrashCan, Add } from "../icons";

const meta = {
  title: "Primitives/IconButton",
  component: IconButton,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
  args: { label: "Button" },
} satisfies Meta<typeof IconButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    label: "Close",
  },
  render: (args) => (
    <IconButton {...args}>
      <Close size={16} />
    </IconButton>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      <IconButton label="Add" kind="primary">
        <Add size={16} />
      </IconButton>
      <IconButton label="Edit" kind="secondary">
        <Edit size={16} />
      </IconButton>
      <IconButton label="Delete" kind="tertiary">
        <TrashCan size={16} />
      </IconButton>
      <IconButton label="Close" kind="ghost">
        <Close size={16} />
      </IconButton>
      <IconButton label="Add (small)" kind="primary" size="sm">
        <Add size={16} />
      </IconButton>
      <IconButton label="Add (large)" kind="primary" size="lg">
        <Add size={16} />
      </IconButton>
      <IconButton label="Disabled" kind="primary" disabled>
        <Add size={16} />
      </IconButton>
    </div>
  ),
};

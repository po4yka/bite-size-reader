import type { Meta, StoryObj } from "@storybook/react-vite";
import { MonoTextArea } from "./MonoTextArea";

const meta = {
  title: "Primitives/MonoTextArea",
  component: MonoTextArea,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof MonoTextArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Notes",
    placeholder: "Enter notes…",
    rows: 4,
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <MonoTextArea labelText="Default" placeholder="Placeholder text" />
      <MonoTextArea labelText="With helper" helperText="Max 500 characters" placeholder="Type something" />
      <MonoTextArea labelText="Invalid" invalid invalidText="Content is required" placeholder="Error state" />
      <MonoTextArea labelText="Disabled" disabled placeholder="Disabled textarea" />
      <MonoTextArea labelText="Tall" rows={8} placeholder="More rows" />
    </div>
  ),
};

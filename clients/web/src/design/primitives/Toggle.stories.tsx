import type { Meta, StoryObj } from "@storybook/react-vite";
import { Toggle } from "./Toggle";

const meta = {
  title: "Primitives/Toggle",
  component: Toggle,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Toggle>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Dark mode",
    labelA: "Off",
    labelB: "On",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Toggle labelText="Default (off)" labelA="Off" labelB="On" />
      <Toggle labelText="Toggled on" labelA="Off" labelB="On" toggled />
      <Toggle labelText="Default toggled on" defaultToggled labelA="Off" labelB="On" />
      <Toggle labelText="Small size" size="sm" labelA="Off" labelB="On" />
      <Toggle labelText="Disabled off" disabled labelA="Off" labelB="On" />
      <Toggle labelText="Disabled on" disabled toggled labelA="Off" labelB="On" />
      <Toggle labelText="Custom labels" labelA="Disabled" labelB="Enabled" />
    </div>
  ),
};

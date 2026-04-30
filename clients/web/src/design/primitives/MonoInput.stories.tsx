import type { Meta, StoryObj } from "@storybook/react-vite";
import { MonoInput } from "./MonoInput";

const meta = {
  title: "Primitives/MonoInput",
  component: MonoInput,
  parameters: { layout: "padded" },
} satisfies Meta<typeof MonoInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Title",
    placeholder: "Enter title…",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <MonoInput labelText="Default" placeholder="Placeholder text" />
      <MonoInput labelText="With helper" helperText="This is helper text" placeholder="Type something" />
      <MonoInput labelText="Invalid" invalid invalidText="This field is required" placeholder="Error state" />
      <MonoInput labelText="Disabled" disabled placeholder="Disabled input" />
      <MonoInput labelText="Hidden label" hideLabel placeholder="Label is visually hidden" />
    </div>
  ),
};

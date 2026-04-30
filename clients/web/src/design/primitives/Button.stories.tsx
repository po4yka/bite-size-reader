import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "./Button";

const meta = {
  title: "Primitives/Button",
  component: Button,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { children: "Submit" },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      <Button kind="primary">Primary</Button>
      <Button kind="secondary">Secondary</Button>
      <Button kind="tertiary">Tertiary</Button>
      <Button kind="ghost">Ghost</Button>
      <Button kind="danger">Danger</Button>
      <Button kind="danger--primary">Danger Primary</Button>
      <Button kind="primary" size="sm">Small</Button>
      <Button kind="primary" size="lg">Large</Button>
      <Button kind="primary" disabled>Disabled</Button>
    </div>
  ),
};

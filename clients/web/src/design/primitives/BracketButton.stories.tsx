import type { Meta, StoryObj } from "@storybook/react-vite";
import { BracketButton } from "./BracketButton";

const meta = {
  title: "Primitives/BracketButton",
  component: BracketButton,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof BracketButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { children: "Submit" } };

export const Variants: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 16 }}>
      <BracketButton>Default</BracketButton>
      <BracketButton kind="secondary">Secondary</BracketButton>
      <BracketButton danger>Danger</BracketButton>
      <BracketButton size="sm">Small</BracketButton>
      <BracketButton size="lg">Large</BracketButton>
      <BracketButton disabled>Disabled</BracketButton>
      <BracketButton isLoading>Loading</BracketButton>
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <BracketButton size="sm">Small</BracketButton>
      <BracketButton size="md">Medium</BracketButton>
      <BracketButton size="lg">Large</BracketButton>
    </div>
  ),
};

export const DangerVariant: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 12 }}>
      <BracketButton danger>Delete</BracketButton>
      <BracketButton danger size="sm">Remove</BracketButton>
      <BracketButton danger disabled>Disabled Danger</BracketButton>
    </div>
  ),
};

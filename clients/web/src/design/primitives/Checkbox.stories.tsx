import type { Meta, StoryObj } from "@storybook/react-vite";
import { Checkbox } from "./Checkbox";

const meta = {
  title: "Primitives/Checkbox",
  component: Checkbox,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof Checkbox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { labelText: "Accept terms and conditions" },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Checkbox labelText="Unchecked" />
      <Checkbox labelText="Checked" defaultChecked />
      <Checkbox labelText="Disabled unchecked" disabled />
      <Checkbox labelText="Disabled checked" disabled defaultChecked />
      <Checkbox
        labelText="With helper text"
        helperText="Optional additional info"
      />
      <Checkbox
        labelText="Invalid"
        invalid
        invalidText="This field is required"
      />
    </div>
  ),
};

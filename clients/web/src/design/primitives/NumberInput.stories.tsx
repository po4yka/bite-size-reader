import type { Meta, StoryObj } from "@storybook/react-vite";
import { NumberInput } from "./NumberInput";

const meta = {
  title: "Primitives/NumberInput",
  component: NumberInput,
  parameters: { layout: "padded" },
} satisfies Meta<typeof NumberInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    label: "Quantity",
    value: 1,
    min: 0,
    max: 100,
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <NumberInput label="Default" value={5} min={0} max={100} />
      <NumberInput label="With helper" value={10} helperText="Enter a value between 0 and 100" min={0} max={100} />
      <NumberInput label="Invalid" value={-1} invalid invalidText="Value must be positive" />
      <NumberInput label="Disabled" value={3} disabled />
      <NumberInput label="No steppers" value={7} hideSteppers />
      <NumberInput label="Custom step" value={0} step={5} min={0} max={50} />
    </div>
  ),
};

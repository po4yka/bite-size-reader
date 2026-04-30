import type { Meta, StoryObj } from "@storybook/react-vite";
import { RadioButton, RadioButtonGroup } from "./RadioButton";

const meta = {
  title: "Primitives/RadioButton",
  component: RadioButton,
  parameters: { layout: "padded" },
  args: { value: "a" },
} satisfies Meta<typeof RadioButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Option A",
    value: "a",
    name: "default-group",
  },
  render: (args) => <RadioButton {...args} />,
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <RadioButtonGroup legendText="Horizontal group" name="h-group" valueSelected="b">
        <RadioButton labelText="Option A" value="a" />
        <RadioButton labelText="Option B" value="b" />
        <RadioButton labelText="Option C" value="c" />
      </RadioButtonGroup>
      <RadioButtonGroup legendText="Vertical group" name="v-group" orientation="vertical" valueSelected="a">
        <RadioButton labelText="Option A" value="a" />
        <RadioButton labelText="Option B" value="b" />
        <RadioButton labelText="Disabled option" value="c" disabled />
      </RadioButtonGroup>
      <RadioButtonGroup legendText="Invalid group" name="invalid-group" invalid invalidText="Please select an option">
        <RadioButton labelText="Option A" value="a" />
        <RadioButton labelText="Option B" value="b" />
      </RadioButtonGroup>
      <RadioButtonGroup legendText="Disabled group" name="disabled-group" disabled>
        <RadioButton labelText="Option A" value="a" />
        <RadioButton labelText="Option B" value="b" />
      </RadioButtonGroup>
    </div>
  ),
};

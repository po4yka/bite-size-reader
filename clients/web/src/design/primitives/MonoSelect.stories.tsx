import type { Meta, StoryObj } from "@storybook/react-vite";
import { MonoSelect, MonoSelectItem } from "./MonoSelect";

const meta = {
  title: "Primitives/MonoSelect",
  component: MonoSelect,
  parameters: { layout: "padded" },
} satisfies Meta<typeof MonoSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Category",
  },
  render: (args) => (
    <MonoSelect {...args}>
      <MonoSelectItem value="" text="Select an option" />
      <MonoSelectItem value="tech" text="Technology" />
      <MonoSelectItem value="science" text="Science" />
      <MonoSelectItem value="culture" text="Culture" />
    </MonoSelect>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <MonoSelect labelText="Default">
        <MonoSelectItem value="" text="Select an option" />
        <MonoSelectItem value="a" text="Option A" />
        <MonoSelectItem value="b" text="Option B" />
      </MonoSelect>
      <MonoSelect labelText="With helper" helperText="Choose one category">
        <MonoSelectItem value="" text="Select category" />
        <MonoSelectItem value="tech" text="Technology" />
        <MonoSelectItem value="science" text="Science" />
      </MonoSelect>
      <MonoSelect labelText="Invalid" invalid invalidText="Selection required">
        <MonoSelectItem value="" text="Select an option" />
        <MonoSelectItem value="a" text="Option A" />
      </MonoSelect>
      <MonoSelect labelText="Disabled" disabled>
        <MonoSelectItem value="a" text="Locked option" />
      </MonoSelect>
    </div>
  ),
};

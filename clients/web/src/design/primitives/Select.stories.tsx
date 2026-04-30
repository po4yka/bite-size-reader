import type { Meta, StoryObj } from "@storybook/react-vite";
import { Select, SelectItem } from "./Select";

const meta = {
  title: "Primitives/Select",
  component: Select,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Sort by",
    children: (
      <>
        <SelectItem value="newest" text="Newest first" />
        <SelectItem value="oldest" text="Oldest first" />
        <SelectItem value="relevance" text="Relevance" />
      </>
    ),
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <Select labelText="Default select">
        <SelectItem value="a" text="Option A" />
        <SelectItem value="b" text="Option B" />
        <SelectItem value="c" text="Option C" />
      </Select>
      <Select labelText="With helper" helperText="Choose the sort order">
        <SelectItem value="asc" text="Ascending" />
        <SelectItem value="desc" text="Descending" />
      </Select>
      <Select labelText="Invalid" invalid invalidText="Selection is required">
        <SelectItem value="" text="Choose one" hidden />
        <SelectItem value="a" text="Option A" />
      </Select>
      <Select labelText="Disabled" disabled>
        <SelectItem value="a" text="Option A" />
      </Select>
      <Select labelText="Hidden label" hideLabel>
        <SelectItem value="a" text="Option A" />
        <SelectItem value="b" text="Option B" />
      </Select>
    </div>
  ),
};

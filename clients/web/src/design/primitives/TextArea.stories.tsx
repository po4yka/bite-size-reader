import type { Meta, StoryObj } from "@storybook/react-vite";
import { TextArea } from "./TextArea";

const meta = {
  title: "Primitives/TextArea",
  component: TextArea,
  parameters: { layout: "padded" },
} satisfies Meta<typeof TextArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Description",
    placeholder: "Enter a description…",
    rows: 4,
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <TextArea labelText="Default" placeholder="Type here…" />
      <TextArea labelText="With helper" helperText="Maximum 500 characters" placeholder="Type here…" />
      <TextArea labelText="Pre-filled" defaultValue="This textarea has existing content that spans multiple lines." />
      <TextArea labelText="Invalid" invalid invalidText="Description is required" placeholder="Type here…" />
      <TextArea labelText="Disabled" disabled defaultValue="This field is read-only." />
      <TextArea labelText="Tall (8 rows)" rows={8} placeholder="Large input area…" />
    </div>
  ),
};

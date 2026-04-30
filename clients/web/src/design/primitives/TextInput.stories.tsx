import type { Meta, StoryObj } from "@storybook/react-vite";
import { TextInput } from "./TextInput";

const meta = {
  title: "Primitives/TextInput",
  component: TextInput,
  parameters: { layout: "padded" },
} satisfies Meta<typeof TextInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelText: "Username",
    placeholder: "Enter username…",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <TextInput labelText="Default" placeholder="Enter value…" />
      <TextInput labelText="With helper" helperText="Must be 3–20 characters" placeholder="Enter username…" />
      <TextInput labelText="Pre-filled" defaultValue="john.doe" />
      <TextInput labelText="Invalid" invalid invalidText="Username is already taken" defaultValue="john.doe" />
      <TextInput labelText="Warning" warn warnText="Username is close to expiry" defaultValue="olduser99" />
      <TextInput labelText="Disabled" disabled defaultValue="readonly.value" />
      <TextInput labelText="Password" type="password" placeholder="Enter password…" />
      <TextInput labelText="Hidden label" hideLabel placeholder="Search…" />
    </div>
  ),
};

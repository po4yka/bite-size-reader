import type { Meta, StoryObj } from "@storybook/react-vite";
import { Search } from "./Search";

const meta = {
  title: "Primitives/Search",
  component: Search,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Search>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Search…",
    labelText: "Search",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Search placeholder="Search articles…" labelText="Search" size="sm" />
      <Search placeholder="Search articles…" labelText="Search" size="md" />
      <Search placeholder="Search articles…" labelText="Search" size="lg" />
      <Search
        placeholder="With initial value"
        labelText="Search"
        defaultValue="react query"
      />
    </div>
  ),
};

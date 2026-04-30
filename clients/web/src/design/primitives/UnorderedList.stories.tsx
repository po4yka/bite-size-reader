import type { Meta, StoryObj } from "@storybook/react-vite";
import { UnorderedList, ListItem } from "./UnorderedList";

const meta = {
  title: "Primitives/UnorderedList",
  component: UnorderedList,
  parameters: { layout: "padded" },
} satisfies Meta<typeof UnorderedList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <UnorderedList>
      <ListItem>First item</ListItem>
      <ListItem>Second item</ListItem>
      <ListItem>Third item</ListItem>
    </UnorderedList>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Default</p>
        <UnorderedList>
          <ListItem>Alpha</ListItem>
          <ListItem>Beta</ListItem>
          <ListItem>Gamma</ListItem>
        </UnorderedList>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Nested</p>
        <UnorderedList>
          <ListItem>
            Parent item
            <UnorderedList nested>
              <ListItem>Child item A</ListItem>
              <ListItem>Child item B</ListItem>
            </UnorderedList>
          </ListItem>
          <ListItem>Another parent</ListItem>
        </UnorderedList>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Expressive</p>
        <UnorderedList isExpressive>
          <ListItem>Larger text rhythm</ListItem>
          <ListItem>Second item</ListItem>
        </UnorderedList>
      </div>
    </div>
  ),
};

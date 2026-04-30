import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tile } from "./Tile";

const meta = {
  title: "Primitives/Tile",
  component: Tile,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Tile>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: (
      <div>
        <h3>Article title</h3>
        <p>A brief summary of the article content.</p>
      </div>
    ),
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Tile>
        <h3>Default tile</h3>
        <p>Standard tile with default styling.</p>
      </Tile>
      <Tile light>
        <h3>Light variant</h3>
        <p>Tile with light background treatment.</p>
      </Tile>
      <Tile>
        <h3>Rich content tile</h3>
        <p>Published: Jan 2, 2025</p>
        <p>
          A longer summary that demonstrates how the tile handles multi-line
          content and various child element types.
        </p>
        <div style={{ marginTop: 8 }}>
          <span>Tag A</span>
          {" "}
          <span>Tag B</span>
        </div>
      </Tile>
    </div>
  ),
};

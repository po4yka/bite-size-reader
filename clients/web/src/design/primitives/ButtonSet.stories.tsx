import type { Meta, StoryObj } from "@storybook/react-vite";
import { ButtonSet } from "./ButtonSet";
import { Button } from "./Button";

const meta = {
  title: "Primitives/ButtonSet",
  component: ButtonSet,
  parameters: { layout: "padded" },
} satisfies Meta<typeof ButtonSet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <ButtonSet>
      <Button kind="primary">Save</Button>
      <Button kind="secondary">Cancel</Button>
    </ButtonSet>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Inline (default)</p>
        <ButtonSet>
          <Button kind="primary">Save</Button>
          <Button kind="secondary">Cancel</Button>
          <Button kind="ghost">Reset</Button>
        </ButtonSet>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Stacked</p>
        <ButtonSet stacked>
          <Button kind="primary">Save</Button>
          <Button kind="secondary">Cancel</Button>
        </ButtonSet>
      </div>
    </div>
  ),
};

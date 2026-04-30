import type { Meta, StoryObj } from "@storybook/react-vite";
import { InlineNotification } from "./InlineNotification";

const meta = {
  title: "Primitives/InlineNotification",
  component: InlineNotification,
  parameters: { layout: "padded" },
} satisfies Meta<typeof InlineNotification>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    kind: "info",
    title: "Information",
    subtitle: "This is an informational message.",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <InlineNotification
        kind="info"
        title="Info"
        subtitle="An informational notice."
      />
      <InlineNotification
        kind="success"
        title="Success"
        subtitle="Operation completed."
      />
      <InlineNotification
        kind="warning"
        title="Warning"
        subtitle="Proceed with caution."
      />
      <InlineNotification
        kind="error"
        title="Error"
        subtitle="Something went wrong."
      />
      <InlineNotification
        kind="info"
        title="No close button"
        subtitle="This notification cannot be dismissed."
        hideCloseButton
      />
    </div>
  ),
};

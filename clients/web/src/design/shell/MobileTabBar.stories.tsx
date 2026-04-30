import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router-dom";
import { MobileTabBar } from "./MobileTabBar";

const meta = {
  title: "Shell/MobileTabBar",
  component: MobileTabBar,
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/library"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: {
    viewport: {
      defaultViewport: "frost-mobile-393",
    },
    layout: "fullscreen",
  },
} satisfies Meta<typeof MobileTabBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const QueueActive: Story = {};

export const DigestsActive: Story = {
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/digest"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
};

export const TopicsActive: Story = {
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/tags"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
};

export const SettingsActive: Story = {
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/preferences"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
};

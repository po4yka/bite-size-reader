import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router-dom";
import { MobileTabBar } from "./MobileTabBar";

const meta = {
  title: "Shell/MobileTabBar",
  component: MobileTabBar,
  parameters: {
    viewport: {
      defaultViewport: "frostMobile",
    },
    layout: "fullscreen",
  },
} satisfies Meta<typeof MobileTabBar>;

export default meta;
type Story = StoryObj<typeof meta>;

const withRouter = (initialPath: string) => (Story: () => React.ReactElement) =>
  (
    <MemoryRouter initialEntries={[initialPath]}>
      <Story />
    </MemoryRouter>
  );

export const QueueActive: Story = {
  decorators: [withRouter("/library")],
};

export const DigestsActive: Story = {
  decorators: [withRouter("/digest")],
};

export const TopicsActive: Story = {
  decorators: [withRouter("/tags")],
};

export const SettingsActive: Story = {
  decorators: [withRouter("/preferences")],
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  FrostSideNav,
  FrostSideNavItems,
  FrostSideNavLink,
  FrostSideNavDivider,
} from "./FrostSideNav";

const meta = {
  title: "Shell/FrostSideNav",
  component: FrostSideNav,
  parameters: { layout: "fullscreen", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof FrostSideNav>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ display: "flex", height: "100vh" }}>
      <FrostSideNav aria-label="Main navigation">
        <FrostSideNavItems>
          <FrostSideNavLink href="/" isActive>Library</FrostSideNavLink>
          <FrostSideNavLink href="/search">Search</FrostSideNavLink>
          <FrostSideNavLink href="/collections">Collections</FrostSideNavLink>
          <FrostSideNavDivider />
          <FrostSideNavLink href="/digest">Digest</FrostSideNavLink>
          <FrostSideNavLink href="/feeds">Feeds</FrostSideNavLink>
          <FrostSideNavDivider />
          <FrostSideNavLink href="/webhooks">Webhooks</FrostSideNavLink>
          <FrostSideNavLink href="/rules">Rules</FrostSideNavLink>
          <FrostSideNavLink href="/signals">Signals</FrostSideNavLink>
          <FrostSideNavDivider />
          <FrostSideNavLink href="/preferences">Preferences</FrostSideNavLink>
        </FrostSideNavItems>
      </FrostSideNav>
      <main style={{ flex: 1, padding: 32, fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>
        Main content area
      </main>
    </div>
  ),
};

export const NoActiveLink: Story = {
  render: () => (
    <div style={{ height: 400, display: "flex" }}>
      <FrostSideNav aria-label="Navigation">
        <FrostSideNavItems>
          <FrostSideNavLink href="/">Library</FrostSideNavLink>
          <FrostSideNavLink href="/search">Search</FrostSideNavLink>
          <FrostSideNavLink href="/collections">Collections</FrostSideNavLink>
        </FrostSideNavItems>
      </FrostSideNav>
    </div>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 32 }}>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Library active
        </p>
        <div style={{ height: 480, display: "flex" }}>
          <FrostSideNav aria-label="Library nav">
            <FrostSideNavItems>
              <FrostSideNavLink href="/" isActive>Library</FrostSideNavLink>
              <FrostSideNavLink href="/search">Search</FrostSideNavLink>
              <FrostSideNavLink href="/collections">Collections</FrostSideNavLink>
              <FrostSideNavDivider />
              <FrostSideNavLink href="/digest">Digest</FrostSideNavLink>
              <FrostSideNavLink href="/feeds">Feeds</FrostSideNavLink>
              <FrostSideNavDivider />
              <FrostSideNavLink href="/preferences">Preferences</FrostSideNavLink>
            </FrostSideNavItems>
          </FrostSideNav>
        </div>
      </div>

      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Settings active
        </p>
        <div style={{ height: 480, display: "flex" }}>
          <FrostSideNav aria-label="Settings nav">
            <FrostSideNavItems>
              <FrostSideNavLink href="/">Library</FrostSideNavLink>
              <FrostSideNavLink href="/search">Search</FrostSideNavLink>
              <FrostSideNavLink href="/collections">Collections</FrostSideNavLink>
              <FrostSideNavDivider />
              <FrostSideNavLink href="/digest">Digest</FrostSideNavLink>
              <FrostSideNavLink href="/feeds">Feeds</FrostSideNavLink>
              <FrostSideNavDivider />
              <FrostSideNavLink href="/preferences" isActive>Preferences</FrostSideNavLink>
            </FrostSideNavItems>
          </FrostSideNav>
        </div>
      </div>
    </div>
  ),
};

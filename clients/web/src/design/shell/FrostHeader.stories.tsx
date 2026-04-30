import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  FrostHeader,
  FrostHeaderName,
  FrostHeaderMenuButton,
  FrostHeaderGlobalBar,
  FrostHeaderGlobalAction,
  FrostSkipToContent,
} from "./FrostHeader";

const meta = {
  title: "Shell/FrostHeader",
  component: FrostHeader,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof FrostHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <FrostHeader aria-label="Ratatoskr">
      <FrostSkipToContent />
      <FrostHeaderMenuButton aria-label="Open menu" />
      <FrostHeaderName href="/" prefix="RTK">
        Ratatoskr
      </FrostHeaderName>
      <FrostHeaderGlobalBar>
        <FrostHeaderGlobalAction aria-label="Search">⌕</FrostHeaderGlobalAction>
        <FrostHeaderGlobalAction aria-label="Settings">⚙</FrostHeaderGlobalAction>
      </FrostHeaderGlobalBar>
    </FrostHeader>
  ),
};

export const WordmarkOnly: Story = {
  render: () => (
    <FrostHeader aria-label="Ratatoskr">
      <FrostHeaderName href="/">Ratatoskr</FrostHeaderName>
    </FrostHeader>
  ),
};

export const WithPrefix: Story = {
  render: () => (
    <FrostHeader aria-label="RTK">
      <FrostHeaderName href="/" prefix="RTK /">
        Library
      </FrostHeaderName>
      <FrostHeaderGlobalBar>
        <FrostHeaderGlobalAction aria-label="Profile">◉</FrostHeaderGlobalAction>
      </FrostHeaderGlobalBar>
    </FrostHeader>
  ),
};

export const ActiveMenuButton: Story = {
  render: () => (
    <FrostHeader aria-label="Ratatoskr">
      <FrostHeaderMenuButton aria-label="Close menu" isActive />
      <FrostHeaderName href="/">Ratatoskr</FrostHeaderName>
    </FrostHeader>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 32 }}>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Full header with menu + global bar
        </p>
        <FrostHeader aria-label="Full">
          <FrostSkipToContent />
          <FrostHeaderMenuButton aria-label="Open menu" />
          <FrostHeaderName href="/" prefix="RTK">Ratatoskr</FrostHeaderName>
          <FrostHeaderGlobalBar>
            <FrostHeaderGlobalAction aria-label="Search">⌕</FrostHeaderGlobalAction>
            <FrostHeaderGlobalAction aria-label="Settings">⚙</FrostHeaderGlobalAction>
          </FrostHeaderGlobalBar>
        </FrostHeader>
      </div>

      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Wordmark only
        </p>
        <FrostHeader aria-label="Minimal">
          <FrostHeaderName href="/">Ratatoskr</FrostHeaderName>
        </FrostHeader>
      </div>

      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Active (menu open) state
        </p>
        <FrostHeader aria-label="Active state">
          <FrostHeaderMenuButton aria-label="Close menu" isActive />
          <FrostHeaderName href="/">Ratatoskr</FrostHeaderName>
          <FrostHeaderGlobalBar>
            <FrostHeaderGlobalAction aria-label="Profile" isActive>◉</FrostHeaderGlobalAction>
          </FrostHeaderGlobalBar>
        </FrostHeader>
      </div>
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import { MonoProgressBar } from "./MonoProgressBar";

const meta = {
  title: "Frost/MonoProgressBar",
  component: MonoProgressBar,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof MonoProgressBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    label: "Importing",
    value: 45,
    helperText: "45 of 100 articles",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 480 }}>
      <MonoProgressBar label="Active" value={60} helperText="60%" />
      <MonoProgressBar label="Complete" value={100} status="finished" helperText="Done" />
      <MonoProgressBar label="Error" value={40} status="error" helperText="Import failed at 40%" />
      <MonoProgressBar label="Indeterminate" helperText="Processing…" />
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Medium (default) — 8px track
        </div>
        <MonoProgressBar label="Medium" value={60} size="medium" helperText="8px tall" />
      </div>
      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Small — 4px track
        </div>
        <MonoProgressBar label="Small" value={60} size="small" helperText="4px tall" />
      </div>
    </div>
  ),
};

export const StatusStates: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Active — solid ink fill, grows left to right
        </div>
        <MonoProgressBar label="Syncing" value={35} helperText="35 of 100" />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Finished — ink fill full width, ✓ appended to label
        </div>
        <MonoProgressBar label="Import" value={100} status="finished" helperText="All articles imported" />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Error — fill becomes spark (full opacity), no red text
        </div>
        <MonoProgressBar label="Upload" value={72} status="error" helperText="Network error at 72%" />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Indeterminate — frost-pulse oscillation 0.4 ↔ 1.0
        </div>
        <MonoProgressBar label="Processing" helperText="Calculating…" />
      </div>
    </div>
  ),
};

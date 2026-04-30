import type { Meta, StoryObj } from "@storybook/react-vite";
import { BrutalistCard } from "./BrutalistCard";

const meta = {
  title: "Frost/BrutalistCard",
  component: BrutalistCard,
  parameters: { layout: "padded" },
} satisfies Meta<typeof BrutalistCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: (
      <div>
        <div style={{ fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", fontSize: 11 }}>
          ARTICLE TITLE
        </div>
        <div style={{ opacity: 0.6, fontSize: 11 }}>2025-04-30 · ratatoskr.io</div>
        <div>A brief summary of the article content rendered in mono body.</div>
      </div>
    ),
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 640 }}>
      <BrutalistCard>
        <div style={{ fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", fontSize: 11 }}>
          DEFAULT STATE
        </div>
        <div style={{ opacity: 0.6, fontSize: 11 }}>1px ink hairline · no shadow · 0 radius</div>
        <div>Standard card with mono body content.</div>
      </BrutalistCard>

      <BrutalistCard state="critical">
        <div style={{ fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", fontSize: 11 }}>
          CRITICAL STATE
        </div>
        <div style={{ opacity: 0.6, fontSize: 11 }}>2px leading spark hairline (left border)</div>
        <div>Critical state card. Spark bar on the leading edge only — no red text.</div>
      </BrutalistCard>

      <BrutalistCard interactive>
        <div style={{ fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", fontSize: 11 }}>
          INTERACTIVE STATE
        </div>
        <div style={{ opacity: 0.6, fontSize: 11 }}>Hover to see hairline thicken to 2px</div>
        <div>Interactive card — border thickens on hover. No color shift.</div>
      </BrutalistCard>

      <BrutalistCard state="critical" interactive>
        <div style={{ fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", fontSize: 11 }}>
          CRITICAL + INTERACTIVE
        </div>
        <div style={{ opacity: 0.6, fontSize: 11 }}>Both modifiers combined</div>
        <div>Critical spark bar with interactive hover behavior.</div>
      </BrutalistCard>
    </div>
  ),
};

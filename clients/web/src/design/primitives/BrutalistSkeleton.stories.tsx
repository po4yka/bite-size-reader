import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  BrutalistSkeleton,
  BrutalistSkeletonText,
  BrutalistSkeletonPlaceholder,
  BrutalistDataTableSkeleton,
} from "./BrutalistSkeleton";

const meta = {
  title: "Frost/BrutalistSkeleton",
  component: BrutalistSkeleton,
  parameters: { layout: "padded" },
} satisfies Meta<typeof BrutalistSkeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    width: "240px",
    height: "1rem",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32, maxWidth: 640 }}>
      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Text — single line
        </div>
        <BrutalistSkeletonText />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Text — paragraph (3 lines)
        </div>
        <BrutalistSkeletonText paragraph lineCount={3} />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Text — heading
        </div>
        <BrutalistSkeletonText heading />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Placeholder — full width block
        </div>
        <BrutalistSkeletonPlaceholder />
      </div>

      <div>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Custom block
        </div>
        <BrutalistSkeleton width="320px" height="48px" />
      </div>
    </div>
  ),
};

export const DataTable: Story = {
  render: () => (
    <div style={{ maxWidth: 640 }}>
      <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
        Data table — hairline frame, stacked rows with hairline dividers
      </div>
      <BrutalistDataTableSkeleton columnCount={4} rowCount={5} />
    </div>
  ),
};

export const SkeletonText: Story = {
  name: "Text variants",
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
      <BrutalistSkeletonText paragraph lineCount={5} />
      <BrutalistSkeletonText paragraph lineCount={2} width="60%" />
      <BrutalistSkeletonText heading />
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import { SkeletonText, SkeletonPlaceholder, DataTableSkeleton } from "./Skeleton";

const meta = {
  title: "Primitives/Skeleton",
  component: SkeletonText,
  parameters: { layout: "padded" },
} satisfies Meta<typeof SkeletonText>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Text: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Single line</p>
        <SkeletonText />
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Heading</p>
        <SkeletonText heading />
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Paragraph (3 lines)</p>
        <SkeletonText paragraph lineCount={3} />
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Custom width</p>
        <SkeletonText width="60%" />
      </div>
    </div>
  ),
};

export const Placeholder: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <SkeletonPlaceholder />
      <SkeletonPlaceholder style={{ width: 200, height: 120 }} />
      <SkeletonPlaceholder style={{ width: "100%", height: 200 }} />
    </div>
  ),
};

export const DataTable: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Default (3 cols, 5 rows)</p>
        <DataTableSkeleton />
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Custom columns</p>
        <DataTableSkeleton columnCount={5} rowCount={3} />
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>No toolbar</p>
        <DataTableSkeleton showToolbar={false} rowCount={4} />
      </div>
    </div>
  ),
};

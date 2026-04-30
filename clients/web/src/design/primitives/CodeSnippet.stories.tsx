import type { Meta, StoryObj } from "@storybook/react-vite";
import { CodeSnippet } from "./CodeSnippet";

const meta = {
  title: "Primitives/CodeSnippet",
  component: CodeSnippet,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof CodeSnippet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    type: "single",
    children: "npm install @tanstack/react-query",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Single line</p>
        <CodeSnippet type="single">
          {"npm install react react-dom"}
        </CodeSnippet>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>Multi line</p>
        <CodeSnippet type="multi">
          {"const query = useQuery({\n  queryKey: ['items'],\n  queryFn: fetchItems,\n});"}
        </CodeSnippet>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>
          Inline: Use <CodeSnippet type="inline">useQuery</CodeSnippet> to fetch data.
        </p>
      </div>
      <div>
        <p style={{ marginBottom: 8, fontSize: 12 }}>No copy button</p>
        <CodeSnippet type="single" hideCopyButton>
          {"read-only snippet"}
        </CodeSnippet>
      </div>
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react-vite";
import { Link } from "./Link";

const meta = {
  title: "Primitives/Link",
  component: Link,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof Link>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    href: "#",
    children: "View article",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Link href="#">Default link — underline at ink @ 0.4</Link>
      <Link href="#" size="sm">Small link (size prop preserved, no visual diff in Frost)</Link>
      <Link href="#" size="lg">Large link</Link>
      <Link href="#" disabled>Disabled link</Link>
      <Link href="#" inline>Inline link used in a sentence context.</Link>
      <Link href="#" target="_blank" rel="noopener noreferrer">
        External link (new tab)
      </Link>
      <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>
        Prose with an <Link href="#">inline link</Link> inheriting parent size and weight.
      </p>
    </div>
  ),
};

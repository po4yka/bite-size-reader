import type { Meta, StoryObj } from "@storybook/react-vite";
import { Accordion, AccordionItem } from "./Accordion";

const meta = {
  title: "Primitives/Accordion",
  component: Accordion,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof Accordion>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Accordion>
      <AccordionItem title="Section one">
        Content for section one.
      </AccordionItem>
    </Accordion>
  ),
};

export const Variants: Story = {
  render: () => (
    <Accordion>
      <AccordionItem title="Collapsed by default">
        This panel starts closed.
      </AccordionItem>
      <AccordionItem title="Open by default" open>
        This panel starts open.
      </AccordionItem>
      <AccordionItem title="Disabled item" disabled>
        This panel cannot be toggled.
      </AccordionItem>
      <AccordionItem title="Multiple children">
        <p>First paragraph of content.</p>
        <p>Second paragraph of content.</p>
      </AccordionItem>
    </Accordion>
  ),
};

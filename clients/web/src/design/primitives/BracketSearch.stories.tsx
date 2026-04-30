import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { BracketSearch } from "./BracketSearch";

const meta = {
  title: "Primitives/BracketSearch",
  component: BracketSearch,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof BracketSearch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Search…",
    value: "",
  },
};

export const Variants: Story = {
  render: () => {
    const [empty, setEmpty] = useState("");
    const [active, setActive] = useState("ratatoskr");

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 480 }}>
        <BracketSearch
          labelText="Empty search"
          placeholder="Search articles…"
          value={empty}
          onChange={(e) => setEmpty(e.target.value)}
          onClear={() => setEmpty("")}
        />
        <BracketSearch
          labelText="Active search"
          placeholder="Search articles…"
          value={active}
          onChange={(e) => setActive(e.target.value)}
          onClear={() => setActive("")}
        />
      </div>
    );
  },
};

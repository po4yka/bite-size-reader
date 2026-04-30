import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  RowDigestWrapper,
  RowDigestHead,
  RowDigestBody,
  RowDigestRow,
  RowDigestCell,
  RowDigestSeparator,
  StructuredListWrapper,
  StructuredListHead,
  StructuredListBody,
  StructuredListRow,
  StructuredListCell,
} from "./RowDigest";

const meta = {
  title: "Frost/RowDigest",
  component: RowDigestWrapper,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof RowDigestWrapper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <RowDigestWrapper ariaLabel="Signal digest" style={{ maxWidth: 640 }}>
      <RowDigestBody>
        <RowDigestRow>
          <RowDigestCell>andromeda-signal</RowDigestCell>
          <RowDigestSeparator />
          <RowDigestCell>processed</RowDigestCell>
          <RowDigestSeparator />
          <RowDigestCell active>2025-04-30</RowDigestCell>
        </RowDigestRow>
      </RowDigestBody>
    </RowDigestWrapper>
  ),
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32, maxWidth: 640 }}>

      {/* With head row */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          WITH HEAD ROW
        </div>
        <RowDigestWrapper ariaLabel="Article list">
          <RowDigestHead>
            <RowDigestRow>
              <RowDigestCell head>Title</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell head>Status</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell head>Date</RowDigestCell>
            </RowDigestRow>
          </RowDigestHead>
          <RowDigestBody>
            <RowDigestRow>
              <RowDigestCell>Andromeda Signal</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell>processed</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell active>2025-04-28</RowDigestCell>
            </RowDigestRow>
            <RowDigestRow>
              <RowDigestCell>Boötes Void</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell>pending</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell active>2025-04-29</RowDigestCell>
            </RowDigestRow>
            <RowDigestRow>
              <RowDigestCell>Cygnus X-1</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell>failed</RowDigestCell>
              <RowDigestSeparator />
              <RowDigestCell active>2025-04-30</RowDigestCell>
            </RowDigestRow>
          </RowDigestBody>
        </RowDigestWrapper>
      </section>

      {/* Legacy API (StructuredList names) */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          LEGACY API (StructuredList names — preserved for Phase 3 codemod)
        </div>
        <StructuredListWrapper ariaLabel="Legacy API demo">
          <StructuredListHead>
            <StructuredListRow head>
              <StructuredListCell head>Source</StructuredListCell>
              <StructuredListCell head>Count</StructuredListCell>
            </StructuredListRow>
          </StructuredListHead>
          <StructuredListBody>
            <StructuredListRow>
              <StructuredListCell>ratatoskr.io</StructuredListCell>
              <StructuredListCell active>142</StructuredListCell>
            </StructuredListRow>
            <StructuredListRow>
              <StructuredListCell>hn.algolia.com</StructuredListCell>
              <StructuredListCell active>89</StructuredListCell>
            </StructuredListRow>
          </StructuredListBody>
        </StructuredListWrapper>
      </section>

      {/* Dense meta row (timestamps, secondary) */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          DENSE META ROW
        </div>
        <RowDigestWrapper>
          <RowDigestBody>
            {["ratatoskr", "hackernews", "lobsters"].map((src) => (
              <RowDigestRow key={src}>
                <RowDigestCell>{src}</RowDigestCell>
                <RowDigestSeparator />
                <RowDigestCell>last fetch 2m ago</RowDigestCell>
                <RowDigestSeparator />
                <RowDigestCell>12 new</RowDigestCell>
                <RowDigestSeparator />
                <RowDigestCell active>active</RowDigestCell>
              </RowDigestRow>
            ))}
          </RowDigestBody>
        </RowDigestWrapper>
      </section>

    </div>
  ),
};

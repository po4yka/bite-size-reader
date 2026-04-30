import { RSSFeedsTab } from "../digest/RSSFeedsTab";

export default function FeedsPage() {
  return (
    <main
      className="feeds-page"
      style={{
        maxWidth: "var(--frost-strip-7)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-emph-size)",
          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
          letterSpacing: "var(--frost-type-mono-emph-tracking)",
          textTransform: "uppercase",
          color: "var(--frost-ink)",
          margin: 0,
        }}
      >
        RSS Feeds
      </h1>
      <RSSFeedsTab />
    </main>
  );
}

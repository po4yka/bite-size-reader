import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Toast } from "./Toast";

const meta = {
  title: "Frost/Toast",
  component: Toast,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: "Sync complete",
    body: "42 articles imported from feed.",
    severity: "info",
    position: "bottom-right",
    persistent: true,
  },
};

export const Variants: Story = {
  render: () => {
    const [shown, setShown] = useState<string[]>(["info", "warn", "alarm"]);
    const dismiss = (key: string) => setShown((s) => s.filter((k) => k !== key));
    return (
      <div style={{ minHeight: 300, position: "relative" }}>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          Three severities — persistent for story visibility
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 400 }}>
          {shown.includes("info") && (
            <div style={{ position: "relative", border: "1px solid var(--frost-ink)", background: "var(--frost-page)" }}>
              <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)" }}>
                <span style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase" }}>Sync complete</span>
                <button onClick={() => dismiss("info")} style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "var(--frost-font-mono)", fontSize: 11 }}>×</button>
              </div>
              <div style={{ padding: "8px 12px", fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>42 articles imported from feed.</div>
            </div>
          )}
          {shown.includes("warn") && (
            <div style={{ position: "relative", border: "1px solid var(--frost-ink)", background: "var(--frost-page)" }}>
              <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)" }}>
                <span style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase" }}>! Feed paused</span>
                <button onClick={() => dismiss("warn")} style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "var(--frost-font-mono)", fontSize: 11 }}>×</button>
              </div>
              <div style={{ padding: "8px 12px", fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>Authentication required for this feed.</div>
            </div>
          )}
          {shown.includes("alarm") && (
            <div style={{ position: "relative", border: "1px solid var(--frost-ink)", borderLeft: "2px solid var(--frost-spark)", background: "var(--frost-page)" }}>
              <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)" }}>
                <span style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase" }}>Import failed</span>
                <button onClick={() => dismiss("alarm")} style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "var(--frost-font-mono)", fontSize: 11 }}>×</button>
              </div>
              <div style={{ padding: "8px 12px", fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>Connection refused. Check source URL.</div>
            </div>
          )}
        </div>
      </div>
    );
  },
};

export const LiveToast: Story = {
  render: () => {
    const [key, setKey] = useState(0);
    return (
      <div style={{ minHeight: 120 }}>
        <button
          onClick={() => setKey((k) => k + 1)}
          style={{
            fontFamily: "var(--frost-font-mono)",
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: "1px",
            textTransform: "uppercase",
            border: "1px solid var(--frost-ink)",
            borderRadius: 0,
            background: "var(--frost-page)",
            color: "var(--frost-ink)",
            padding: "6px 12px",
            cursor: "pointer",
          }}
        >
          [ Trigger Toast ]
        </button>
        {key > 0 && (
          <Toast
            key={key}
            title="Action complete"
            body="The operation finished successfully."
            severity="info"
            position="bottom-right"
            durationMs={3000}
          />
        )}
      </div>
    );
  },
};

export const Positions: Story = {
  render: () => (
    <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55 }}>
      Use the Live Toast story to test positioning. Rendered inline below for reference:
      <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 400, marginTop: 16 }}>
        {(["top-right", "bottom-right", "bottom-center"] as const).map((pos) => (
          <Toast
            key={pos}
            title={pos}
            body={`Position: ${pos}`}
            severity="info"
            position={pos}
            persistent
            style={{ position: "relative", top: "auto", right: "auto", bottom: "auto", left: "auto", transform: "none" }}
          />
        ))}
      </div>
    </div>
  ),
};

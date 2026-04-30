import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

interface StorybookIndexEntry {
  id: string;
  title: string;
  name: string;
  importPath: string;
  type: "story" | "docs";
}
interface StorybookIndex {
  v: number;
  entries: Record<string, StorybookIndexEntry>;
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STORYBOOK_STATIC = path.resolve(__dirname, "../../../storybook-static");
const indexPath = path.join(STORYBOOK_STATIC, "index.json");

// Read the index synchronously at module load — Playwright needs to know
// the test list at config time.
const index: StorybookIndex = JSON.parse(fs.readFileSync(indexPath, "utf-8"));

const stories = Object.values(index.entries).filter((e) => e.type === "story");

for (const story of stories) {
  test(`storybook visual: ${story.title} — ${story.name}`, async ({ page }) => {
    // Storybook's iframe URL pattern
    await page.goto(`/iframe.html?id=${story.id}&viewMode=story`);
    // Wait for the story root to render
    await page.waitForSelector("#storybook-root", { state: "attached" });
    // Allow fonts + animations to settle
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(150); // small settle for frost-pulse / blinker animations
    await expect(page).toHaveScreenshot(`${story.id}.png`, {
      fullPage: false,
      animations: "disabled",
      maxDiffPixels: 100,
    });
  });
}

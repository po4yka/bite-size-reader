import { test, expect } from "@playwright/test";

const ROUTES = [
  "/library",
  "/articles",
  "/search",
  "/tags",
  "/collections",
  "/submit",
  "/import-export",
  "/backups",
  "/feeds",
  "/preferences",
  "/digest",
  "/admin",
  "/webhooks",
  "/rules",
  "/signals",
  "/login",
];

for (const route of ROUTES) {
  test(`mobile route: ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    // Capture screenshot — first run sets the baseline; later runs diff against it.
    await expect(page).toHaveScreenshot(
      `mobile${route.replace(/\//g, "-")}.png`,
      {
        fullPage: true,
        maxDiffPixels: 100,
      },
    );
  });
}

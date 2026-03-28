import { expect, test } from "@playwright/test";

function successEnvelope(data: unknown) {
  return {
    success: true,
    data,
    meta: {
      timestamp: "2026-03-07T00:00:00Z",
      version: "1.0",
    },
  };
}

test("renders login route", async ({ page }) => {
  await page.goto("login");
  await expect(page.getByText("Sign in to Bite-Size Reader")).toBeVisible();
});

test("loads library after jwt bootstrap", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "bsr_web_auth_tokens",
      JSON.stringify({
        accessToken: "test-access",
        refreshToken: "test-refresh",
        expiresIn: 3600,
        tokenType: "Bearer",
        sessionId: 1,
      }),
    );
  });

  await page.route("**/v1/auth/me", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        successEnvelope({
          userId: 123,
          username: "tester",
          clientId: "web-carbon-v1",
          isOwner: true,
          createdAt: "2026-03-07T00:00:00Z",
        }),
      ),
    });
  });

  await page.route("**/v1/summaries**", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        successEnvelope({
          summaries: [
            {
              id: 1,
              requestId: 11,
              title: "Example Summary",
              url: "https://example.com",
              domain: "example.com",
              tldr: "Summary",
              summary250: "Summary",
              topicTags: ["tech"],
              readingTimeMin: 5,
              isRead: false,
              isFavorited: false,
              lang: "en",
              createdAt: "2026-03-07T00:00:00Z",
            },
          ],
          pagination: {
            total: 1,
            limit: 20,
            offset: 0,
            hasMore: false,
          },
        }),
      ),
    });
  });

  await page.goto("library");

  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
});

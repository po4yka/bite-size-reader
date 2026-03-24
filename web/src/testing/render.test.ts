import { describe, expect, it } from "vitest";
import { useNavigate } from "react-router-dom";
import { renderHookWithProviders, mockTelegramWebApp, createTestQueryClient } from "./render";

describe("createTestQueryClient", () => {
  it("returns a QueryClient with retry disabled", () => {
    const client = createTestQueryClient();
    expect(client.getDefaultOptions().queries?.retry).toBe(false);
  });
});

describe("renderHookWithProviders", () => {
  it("provides MemoryRouter context so useNavigate works", () => {
    const { result } = renderHookWithProviders(() => useNavigate());
    expect(typeof result.current).toBe("function");
  });
});

describe("mockTelegramWebApp", () => {
  it("sets window.Telegram.WebApp and cleans up", () => {
    const cleanup = mockTelegramWebApp({ initData: "my-data" });
    const win = window as unknown as Record<string, unknown> & { Telegram?: { WebApp?: { initData?: string } } };
    expect(win.Telegram?.WebApp?.initData).toBe("my-data");
    cleanup();
    expect(win.Telegram).toBeUndefined();
  });
});

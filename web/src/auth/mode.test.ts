import { describe, expect, it } from "vitest";
import { detectAuthMode } from "./mode";

describe("detectAuthMode", () => {
  it("returns telegram-webapp when initData is present", () => {
    const fakeWindow = {
      Telegram: {
        WebApp: {
          initData: "query=abc",
        },
      },
    } as unknown as Window;

    expect(detectAuthMode(fakeWindow)).toBe("telegram-webapp");
  });

  it("returns jwt when initData is absent", () => {
    const fakeWindow = {} as Window;
    expect(detectAuthMode(fakeWindow)).toBe("jwt");
  });
});

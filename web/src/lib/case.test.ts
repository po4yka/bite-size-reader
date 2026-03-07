import { describe, expect, it } from "vitest";
import { normalizeKeys } from "./case";

describe("normalizeKeys", () => {
  it("normalizes nested snake_case keys", () => {
    const data = {
      summary_id: 1,
      created_at: "now",
      nested_value: {
        item_count: 2,
        child_items: [{ first_name: "Alice" }],
      },
    };

    expect(normalizeKeys(data)).toEqual({
      summaryId: 1,
      createdAt: "now",
      nestedValue: {
        itemCount: 2,
        childItems: [{ firstName: "Alice" }],
      },
    });
  });
});

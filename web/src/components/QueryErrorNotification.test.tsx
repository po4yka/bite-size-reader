import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryErrorNotification } from "./QueryErrorNotification";

describe("QueryErrorNotification", () => {
  it("renders nothing when error is null", () => {
    const { container } = render(<QueryErrorNotification error={null} title="Fail" />);
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when error is undefined", () => {
    const { container } = render(<QueryErrorNotification error={undefined} title="Fail" />);
    expect(container.innerHTML).toBe("");
  });

  it("renders error notification for Error instances", () => {
    render(<QueryErrorNotification error={new Error("connection lost")} title="Network error" />);
    expect(screen.getByText("Network error")).toBeInTheDocument();
    expect(screen.getByText("connection lost")).toBeInTheDocument();
  });

  it("renders error notification for string errors", () => {
    render(<QueryErrorNotification error="something broke" title="Error" />);
    expect(screen.getByText("something broke")).toBeInTheDocument();
  });

  it("displays Unknown error for non-string non-Error values", () => {
    render(<QueryErrorNotification error={42} title="Error" />);
    expect(screen.getByText("Unknown error")).toBeInTheDocument();
  });
});

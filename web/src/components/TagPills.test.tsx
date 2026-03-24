import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TagPills from "./TagPills";

describe("TagPills", () => {
  it("renders nothing when tags array is empty", () => {
    const { container } = render(<TagPills tags={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders a tag for each item", () => {
    const tags = [
      { id: 1, name: "react", color: null },
      { id: 2, name: "typescript", color: null },
    ];
    render(<TagPills tags={tags} />);
    expect(screen.getByText("react")).toBeInTheDocument();
    expect(screen.getByText("typescript")).toBeInTheDocument();
  });

  it("calls onRemove with correct tag id when dismiss is triggered", async () => {
    const user = userEvent.setup();
    const handleRemove = vi.fn();
    const tags = [{ id: 7, name: "removable", color: null }];
    render(<TagPills tags={tags} onRemove={handleRemove} />);

    // Carbon Tag with filter=true renders a dismiss/close button
    const closeButton = screen.getByRole("button");
    await user.click(closeButton);
    expect(handleRemove).toHaveBeenCalledWith(7);
  });

  it("does not render dismiss buttons when onRemove is undefined", () => {
    const tags = [{ id: 1, name: "no-remove", color: null }];
    render(<TagPills tags={tags} />);
    const buttons = screen.queryAllByRole("button");
    expect(buttons).toHaveLength(0);
  });
});

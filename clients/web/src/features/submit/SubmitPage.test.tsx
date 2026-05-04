import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../testing/render";
import SubmitPage from "./SubmitPage";
import type { SubmitQueuedResult } from "../../api/requests";

vi.mock("../../api/requests", () => ({
  checkDuplicate: vi.fn(),
  fetchRequestStatus: vi.fn(),
  retryRequest: vi.fn(),
  submitForward: vi.fn(),
  submitUrl: vi.fn(),
}));

// SubmitPage uses Telegram hooks; stub them so the component renders cleanly.
vi.mock("../../hooks/useTelegramClosingConfirmation", () => ({
  useTelegramClosingConfirmation: vi.fn(),
}));

vi.mock("../../hooks/useTelegramMainButton", () => ({
  useTelegramMainButton: vi.fn(),
}));

const { submitUrl, fetchRequestStatus } = await import("../../api/requests");
const submitUrlMock = vi.mocked(submitUrl);
const fetchStatusMock = vi.mocked(fetchRequestStatus);

describe("SubmitPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("happy path: submits URL, polls for completion, and shows Open summary button", async () => {
    const user = userEvent.setup();

    const queuedResult: SubmitQueuedResult = {
      kind: "queued",
      requestId: "test-req-123",
      status: "pending",
      correlationId: "corr-abc",
      estimatedWaitSeconds: null,
      createdAt: null,
    };
    submitUrlMock.mockResolvedValueOnce(queuedResult);

    fetchStatusMock.mockResolvedValue({
      requestId: "test-req-123",
      status: "completed",
      progressPct: 100,
      summaryId: 456,
      errorMessage: null,
      queuePosition: null,
      estimatedSecondsRemaining: null,
      canRetry: false,
      retryable: null,
      correlationId: "corr-abc",
      updatedAt: null,
      errorType: null,
      errorReasonCode: null,
    });

    renderWithProviders(<SubmitPage />);

    await user.type(screen.getByLabelText(/Article or YouTube URL/i), "https://example.com/article");
    await user.click(screen.getByRole("button", { name: /Summarize/i }));

    expect(submitUrlMock).toHaveBeenCalledWith("https://example.com/article", "auto");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Open summary/i })).toBeInTheDocument();
    });
  });

  it("shows submission error when API returns a failure", async () => {
    const user = userEvent.setup();

    submitUrlMock.mockRejectedValueOnce(new Error("422 Unprocessable Entity"));

    renderWithProviders(<SubmitPage />);

    await user.type(screen.getByLabelText(/Article or YouTube URL/i), "https://example.com/article");
    await user.click(screen.getByRole("button", { name: /Summarize/i }));

    await waitFor(() => {
      expect(screen.getByText(/Submission failed/i)).toBeInTheDocument();
    });

    expect(submitUrlMock).toHaveBeenCalledTimes(1);
  });

  it("prevents submission and shows validation error for an invalid URL", async () => {
    const user = userEvent.setup();

    renderWithProviders(<SubmitPage />);

    const input = screen.getByLabelText(/Article or YouTube URL/i);
    await user.type(input, "not a url !!!");
    await user.tab(); // trigger onBlur to surface validation

    await waitFor(() => {
      expect(screen.getByText(/Enter a valid URL/i)).toBeInTheDocument();
    });

    // Summarize button must be disabled — no API call made.
    expect(screen.getByRole("button", { name: /Summarize/i })).toBeDisabled();
    expect(submitUrlMock).not.toHaveBeenCalled();
  });
});

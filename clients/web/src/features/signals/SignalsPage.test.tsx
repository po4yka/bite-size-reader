import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignalsPage from "./SignalsPage";
import { renderWithProviders } from "../../testing/render";
import {
  fetchSignalHealth,
  fetchSignalSourceHealth,
  fetchSignals,
  setSignalSourceActive,
  updateSignalFeedback,
  upsertSignalTopic,
} from "../../api/signals";

vi.mock("../../api/signals", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/signals")>();
  return {
    ...actual,
    fetchSignals: vi.fn(),
    fetchSignalHealth: vi.fn(),
    fetchSignalSourceHealth: vi.fn(),
    updateSignalFeedback: vi.fn(),
    setSignalSourceActive: vi.fn(),
    upsertSignalTopic: vi.fn(),
  };
});

const mockedFetchSignals = vi.mocked(fetchSignals);
const mockedFetchHealth = vi.mocked(fetchSignalHealth);
const mockedFetchSources = vi.mocked(fetchSignalSourceHealth);
const mockedFeedback = vi.mocked(updateSignalFeedback);
const mockedSourceActive = vi.mocked(setSignalSourceActive);
const mockedTopic = vi.mocked(upsertSignalTopic);

function primeSignalMocks() {
  mockedFetchSignals.mockResolvedValue({
    signals: [
      {
        id: 11,
        status: "candidate",
        heuristicScore: 0.8,
        llmScore: null,
        finalScore: 0.86,
        filterStage: "heuristic",
        feedItemTitle: "SQLite migrations for self-hosted readers",
        feedItemUrl: "https://example.com/migrations",
        sourceKind: "rss",
        sourceTitle: "Infra Notes",
        topicName: "Self-hosting",
      },
    ],
  });
  mockedFetchHealth.mockResolvedValue({
    chroma: { ready: true, required: true, collection: "notes_test" },
    sources: { total: 1, active: 1, errored: 1 },
  });
  mockedFetchSources.mockResolvedValue({
    sources: [
      {
        id: 5,
        kind: "rss",
        externalId: "https://example.com/feed.xml",
        url: "https://example.com/feed.xml",
        title: "Infra Notes",
        isActive: true,
        fetchErrorCount: 1,
        lastError: "timeout",
        lastFetchedAt: null,
        lastSuccessfulAt: null,
        subscriptionId: 20,
        subscriptionActive: true,
        cadenceSeconds: null,
        nextFetchAt: null,
      },
    ],
  });
  mockedFeedback.mockResolvedValue({ updated: true });
  mockedSourceActive.mockResolvedValue({ updated: true, isActive: false });
  mockedTopic.mockResolvedValue({ topic: { id: 1 } });
}

describe("SignalsPage", () => {
  it("renders queue, health, source controls, and writes feedback", async () => {
    const user = userEvent.setup();
    primeSignalMocks();

    renderWithProviders(<SignalsPage />);

    expect(await screen.findByText("SQLite migrations for self-hosted readers")).toBeInTheDocument();
    expect(screen.getByText("86%")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Like" }));
    await waitFor(() => expect(mockedFeedback).toHaveBeenCalledWith(11, "like"));

    await user.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(mockedSourceActive).toHaveBeenCalledWith(5, false));
  });

  it("shows the Chroma unavailable state", async () => {
    primeSignalMocks();
    mockedFetchHealth.mockResolvedValueOnce({
      chroma: { ready: false, required: true, collection: null },
      sources: { total: 0, active: 0, errored: 0 },
    });

    renderWithProviders(<SignalsPage />);

    expect(await screen.findByText("Signal scoring is paused")).toBeInTheDocument();
  });
});

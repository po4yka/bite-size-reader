import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTestQueryClient } from "../testing/render";
import RouteGuard from "./RouteGuard";
import type { AuthMode, AuthStatus } from "./types";

const mockUseAuth = vi.fn<() => { mode: AuthMode; status: AuthStatus }>();

vi.mock("./AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

function authState(status: AuthStatus, mode: AuthMode = "jwt") {
  return {
    mode,
    status,
    user: status === "authenticated" ? { userId: 1, username: "t", clientId: "w", isOwner: true, createdAt: "" } : null,
    tokens: null,
    error: null,
    login: vi.fn(),
    loginWithSecret: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
    dismissError: vi.fn(),
  };
}

function renderGuard(initialEntry = "/library") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/library"
            element={
              <RouteGuard>
                <div>Protected</div>
              </RouteGuard>
            }
          />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RouteGuard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading indicator when auth status is loading", () => {
    mockUseAuth.mockReturnValue(authState("loading"));
    renderGuard();

    expect(screen.getByText(/checking session/i)).toBeInTheDocument();
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    mockUseAuth.mockReturnValue(authState("authenticated"));
    renderGuard();

    expect(screen.getByText("Protected")).toBeInTheDocument();
  });

  it("redirects to login when unauthenticated", () => {
    mockUseAuth.mockReturnValue(authState("unauthenticated"));
    renderGuard();

    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });
});

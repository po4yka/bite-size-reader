import { type ReactElement, type ReactNode } from "react";
import { vi } from "vitest";
import { render, renderHook, type RenderOptions, type RenderHookOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

/** Create a QueryClient configured for tests: no retries, no GC delay. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export interface ProviderOptions {
  queryClient?: QueryClient;
  initialEntries?: MemoryRouterProps["initialEntries"];
}

function TestProviders({
  children,
  queryClient,
  initialEntries,
}: { children: ReactNode } & ProviderOptions) {
  const client = queryClient ?? createTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries ?? ["/"]}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** render() wrapped with QueryClientProvider + MemoryRouter. */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & ProviderOptions,
) {
  const { queryClient, initialEntries, ...renderOptions } = options ?? {};
  const queryClientInstance = queryClient ?? createTestQueryClient();
  return {
    queryClient: queryClientInstance,
    ...render(ui, {
      wrapper: ({ children }) => (
        <TestProviders queryClient={queryClientInstance} initialEntries={initialEntries}>
          {children}
        </TestProviders>
      ),
      ...renderOptions,
    }),
  };
}

/** renderHook() wrapped with QueryClientProvider + MemoryRouter. */
export function renderHookWithProviders<TResult, TProps>(
  hook: (props: TProps) => TResult,
  options?: Omit<RenderHookOptions<TProps>, "wrapper"> & ProviderOptions,
) {
  const { queryClient, initialEntries, ...hookOptions } = options ?? {};
  const queryClientInstance = queryClient ?? createTestQueryClient();
  return {
    queryClient: queryClientInstance,
    ...renderHook(hook, {
      wrapper: ({ children }) => (
        <TestProviders queryClient={queryClientInstance} initialEntries={initialEntries}>
          {children}
        </TestProviders>
      ),
      ...hookOptions,
    }),
  };
}

interface TelegramWebAppMock {
  initData: string;
  colorScheme: string;
  themeParams: Record<string, string>;
  BackButton: { show: ReturnType<typeof vi.fn>; hide: ReturnType<typeof vi.fn>; onClick: ReturnType<typeof vi.fn>; offClick: ReturnType<typeof vi.fn> };
  MainButton: { show: ReturnType<typeof vi.fn>; hide: ReturnType<typeof vi.fn>; setText: ReturnType<typeof vi.fn>; onClick: ReturnType<typeof vi.fn>; offClick: ReturnType<typeof vi.fn> };
  onEvent: ReturnType<typeof vi.fn>;
  offEvent: ReturnType<typeof vi.fn>;
  ready: ReturnType<typeof vi.fn>;
  expand: ReturnType<typeof vi.fn>;
}

/** Mock window.Telegram.WebApp for tests. Returns cleanup function. */
export function mockTelegramWebApp(overrides?: Partial<TelegramWebAppMock>): () => void {
  const mock: TelegramWebAppMock = {
    initData: "test-init-data",
    colorScheme: "light",
    themeParams: {},
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    MainButton: { show: vi.fn(), hide: vi.fn(), setText: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    onEvent: vi.fn(),
    offEvent: vi.fn(),
    ready: vi.fn(),
    expand: vi.fn(),
    ...overrides,
  };

  const win = window as unknown as Record<string, unknown>;
  const prev = win.Telegram;
  win.Telegram = { WebApp: mock };

  return () => {
    if (prev === undefined) {
      delete win.Telegram;
    } else {
      win.Telegram = prev;
    }
  };
}

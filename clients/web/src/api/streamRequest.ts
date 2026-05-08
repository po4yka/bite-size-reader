import { fetchEventSource, EventStreamContentType } from "@microsoft/fetch-event-source";

import { getApiSession, setApiSession } from "./session";
import { getStoredTokens, setStoredTokens } from "../auth/storage";
import { config } from "../lib/config";
import type { components } from "./generated";

type StreamPhaseEvent = components["schemas"]["StreamPhaseEvent"];
type StreamSectionEvent = components["schemas"]["StreamSectionEvent"];
type StreamDoneEvent = components["schemas"]["StreamDoneEvent"];
type StreamErrorEvent = components["schemas"]["StreamErrorEvent"];

const BASE_URL = config.apiBaseUrl;

export interface StreamHandlers {
  onPhase?: (event: StreamPhaseEvent) => void;
  onSection?: (event: StreamSectionEvent) => void;
  onDone?: (event: StreamDoneEvent) => void;
  onError?: (event: StreamErrorEvent) => void;
  onClose?: (cause: "terminal" | "manual" | "fatal") => void;
}

// Exponential backoff: 250ms, 500ms, 1s, 2s, cap at 5s
const BACKOFF_BASE_MS = 250;
const BACKOFF_MAX_MS = 5_000;

function backoffMs(attempt: number): number {
  return Math.min(BACKOFF_BASE_MS * Math.pow(2, attempt), BACKOFF_MAX_MS);
}

async function doRefreshAccessToken(): Promise<string | null> {
  const session = getApiSession();
  const refreshToken = session.refreshToken;

  const response = await fetch(`${BASE_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
    credentials: "same-origin",
    signal: AbortSignal.timeout(20_000),
  });

  if (!response.ok) return null;

  interface RefreshBody {
    data?: { tokens?: { access_token?: string; accessToken?: string } };
  }
  const body = (await response.json()) as RefreshBody;
  const newToken = body?.data?.tokens?.access_token ?? body?.data?.tokens?.accessToken ?? null;
  if (!newToken) return null;

  const previousEnvelope = getStoredTokens();
  const persistent = previousEnvelope?.persistent ?? true;

  const current = getApiSession();
  setApiSession({ ...current, accessToken: newToken });

  if (previousEnvelope) {
    setStoredTokens({ ...previousEnvelope, accessToken: newToken }, { persistent });
  }

  return newToken;
}

export function subscribeToRequest(
  requestId: number | string,
  handlers: StreamHandlers,
): () => void {
  const controller = new AbortController();
  let cancelled = false;
  let retryAttempt = 0;
  let refreshAttempted = false;
  let hadSuccessfulEvent = false;

  function cancel(): void {
    cancelled = true;
    controller.abort();
  }

  async function connect(): Promise<void> {
    if (cancelled) return;

    const session = getApiSession();
    const headers: Record<string, string> = {};

    if (session.mode === "jwt" && session.accessToken) {
      headers["Authorization"] = `Bearer ${session.accessToken}`;
    }

    await fetchEventSource(`${BASE_URL}/v1/requests/${requestId}/stream`, {
      signal: controller.signal,
      openWhenHidden: true,
      headers,

      async onopen(response) {
        if (response.ok && response.headers.get("content-type")?.includes(EventStreamContentType)) {
          // Connection opened successfully; reset backoff
          retryAttempt = 0;
          hadSuccessfulEvent = false;
          return;
        }

        if (response.status === 401 && !refreshAttempted) {
          refreshAttempted = true;
          const newToken = await doRefreshAccessToken();
          if (!newToken) {
            handlers.onClose?.("fatal");
            cancel();
            return;
          }
          // Retry with new token — throw to trigger onerror reconnect
          throw new Error("401-refreshed");
        }

        // Non-retryable: content type mismatch or unrecoverable status
        handlers.onClose?.("fatal");
        cancel();
        throw new Error(`Unretryable response: ${response.status}`);
      },

      onmessage(ev) {
        hadSuccessfulEvent = true;
        retryAttempt = 0; // reset backoff on successful event

        try {
          const data = JSON.parse(ev.data) as unknown;
          const eventType = ev.event;

          if (eventType === "phase") {
            handlers.onPhase?.(data as StreamPhaseEvent);
          } else if (eventType === "section") {
            handlers.onSection?.(data as StreamSectionEvent);
          } else if (eventType === "done") {
            handlers.onDone?.(data as StreamDoneEvent);
            handlers.onClose?.("terminal");
            cancel();
          } else if (eventType === "error") {
            handlers.onError?.(data as StreamErrorEvent);
            handlers.onClose?.("terminal");
            cancel();
          }
        } catch {
          // Malformed JSON — ignore individual event
        }
      },

      onclose() {
        if (cancelled) return;
        // Server closed without a done/error event — treat as terminal
        handlers.onClose?.("terminal");
      },

      onerror(err) {
        if (cancelled) return;

        // Return = retry, throw = stop. We return a delay-Promise so fetch-event-source
        // awaits it before reconnecting, giving us inline exponential backoff.
        const delay = backoffMs(retryAttempt);
        retryAttempt++;

        if (!hadSuccessfulEvent && refreshAttempted && retryAttempt > 3) {
          handlers.onClose?.("fatal");
          cancel();
          throw err;
        }

        return new Promise<void>((resolve) => {
          window.setTimeout(resolve, delay);
        }) as unknown as void;
      },
    });
  }

  void connect();

  return cancel;
}

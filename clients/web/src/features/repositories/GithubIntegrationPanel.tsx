import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BracketButton,
  BracketTabs,
  BracketTab,
  BracketTabList,
  BracketTabPanels,
  BracketTabPanel,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoInput,
  StatusBadge,
} from "../../design";
import {
  getGithubStatus,
  connectGithubPat,
  disconnectGithub,
  startDeviceFlow,
  pollDeviceFlow,
} from "../../api/github";
import type { DeviceFlowStartResponse, DeviceFlowPollStatus } from "../../api/github";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

/* ─── style helpers ─────────────────────────────────────────────────── */

const sectionLabel: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: "0 0 8px",
};

const monoBody: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  lineHeight: "130%",
  letterSpacing: "0.4px",
  color: "var(--frost-ink)",
  margin: 0,
};

/* ─── DeviceFlow sub-panel ──────────────────────────────────────────── */

function DeviceFlowPanel({ onSuccess }: { onSuccess: () => void }) {
  const [flow, setFlow] = useState<DeviceFlowStartResponse | null>(null);
  const [pollStatus, setPollStatus] = useState<DeviceFlowPollStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(true);
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => { onSuccessRef.current = onSuccess; }, [onSuccess]);

  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (pollIntervalRef.current) clearTimeout(pollIntervalRef.current);
    };
  }, []);

  // Stable imperative helpers — stored in refs so recursive calls never go stale
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearTimeout(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const schedulePollRef = useRef<(deviceCode: string, intervalSec: number) => void>(() => {});

  useEffect(() => {
    schedulePollRef.current = function schedulePoll(deviceCode: string, intervalSec: number) {
      if (pollIntervalRef.current) clearTimeout(pollIntervalRef.current);
      pollIntervalRef.current = setTimeout(async () => {
        if (!activeRef.current) return;
        try {
          const res = await pollDeviceFlow(deviceCode);
          if (!activeRef.current) return;
          setPollStatus(res.status);
          if (res.status === "ok") {
            if (pollIntervalRef.current) clearTimeout(pollIntervalRef.current);
            pollIntervalRef.current = null;
            onSuccessRef.current();
          } else if (res.status === "slow_down") {
            schedulePollRef.current(deviceCode, intervalSec + 5);
          } else if (res.status === "pending") {
            schedulePollRef.current(deviceCode, intervalSec);
          } else {
            if (pollIntervalRef.current) clearTimeout(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
        } catch {
          if (!activeRef.current) return;
          setError("Polling failed. Try again.");
          if (pollIntervalRef.current) clearTimeout(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }, intervalSec * 1000);
    };
  }, []);

  async function handleStart() {
    setIsStarting(true);
    setError(null);
    setFlow(null);
    setPollStatus(null);
    try {
      const res = await startDeviceFlow();
      setFlow(res);
      try {
        await navigator.clipboard.writeText(res.user_code);
      } catch {
        // clipboard not available — no-op
      }
      schedulePollRef.current(res.device_code, res.interval);
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      if (status === 503) {
        setError(
          "OAuth Device Flow requires Redis to be configured. Use PAT instead.",
        );
      } else {
        setError("Failed to start device flow. Try again.");
      }
    } finally {
      setIsStarting(false);
    }
  }

  function handleRestart() {
    stopPolling();
    setFlow(null);
    setPollStatus(null);
    setError(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {!flow && !error && (
        <BracketButton
          size="sm"
          isLoading={isStarting}
          onClick={() => void handleStart()}
          aria-label="Start GitHub Device Flow"
        >
          Start Device Flow
        </BracketButton>
      )}

      {error && (
        <>
          <StatusBadge severity="alarm" title="Error">
            {error}
          </StatusBadge>
          {error.includes("Redis") ? null : (
            <BracketButton size="sm" onClick={handleRestart} aria-label="Restart device flow">
              Retry
            </BracketButton>
          )}
        </>
      )}

      {flow && !error && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div>
            <p style={sectionLabel}>Your code</p>
            <p
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "24px",
                fontWeight: 800,
                letterSpacing: "4px",
                margin: "0 0 4px",
              }}
              aria-label="Device verification code"
            >
              {flow.user_code}
            </p>
            <p
              style={{
                ...monoBody,
                fontSize: "11px",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              }}
            >
              (copied to clipboard)
            </p>
          </div>

          <p style={monoBody}>
            Open{" "}
            <a
              href={flow.verification_uri}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--frost-ink)", fontWeight: 800 }}
            >
              {flow.verification_uri}
            </a>{" "}
            and enter the code above.
          </p>

          {pollStatus === "pending" || pollStatus === "slow_down" ? (
            <StatusBadge severity="info" title="Waiting">
              Waiting for authorization…
            </StatusBadge>
          ) : pollStatus === "expired" ? (
            <>
              <StatusBadge severity="alarm" title="Expired">
                Code expired.
              </StatusBadge>
              <BracketButton size="sm" onClick={handleRestart} aria-label="Restart device flow">
                Restart
              </BracketButton>
            </>
          ) : pollStatus === "denied" ? (
            <>
              <StatusBadge severity="alarm" title="Denied">
                Authorization denied.
              </StatusBadge>
              <BracketButton size="sm" onClick={handleRestart} aria-label="Restart device flow">
                Restart
              </BracketButton>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

/* ─── PAT sub-panel ─────────────────────────────────────────────────── */

function PATPanel({ onSuccess }: { onSuccess: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  async function handleSubmit() {
    if (!token.trim()) {
      setError("Token is required.");
      return;
    }
    setIsLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await connectGithubPat(token.trim());
      setSuccessMsg(`Connected as ${res.login}`);
      setToken("");
      onSuccess();
    } catch (err: unknown) {
      const message = (err as { message?: string })?.message ?? "";
      setError(message || "Failed to connect PAT. Check the token and try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <MonoInput
        id="github-pat"
        labelText="Personal Access Token"
        type="password"
        placeholder="ghp_…"
        value={token}
        onChange={(e) => setToken(e.currentTarget.value)}
        onKeyDown={(e) => { if (e.key === "Enter") void handleSubmit(); }}
        disabled={isLoading}
        invalid={Boolean(error)}
        invalidText={error ?? undefined}
        aria-label="GitHub Personal Access Token"
      />
      {successMsg && (
        <StatusBadge severity="info" title="Connected">
          {successMsg}
        </StatusBadge>
      )}
      <BracketButton
        size="sm"
        isLoading={isLoading}
        onClick={() => void handleSubmit()}
        aria-label="Connect with Personal Access Token"
      >
        Connect
      </BracketButton>
    </div>
  );
}

/* ─── main panel ────────────────────────────────────────────────────── */

export default function GithubIntegrationPanel() {
  const queryClient = useQueryClient();
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const statusQuery = useQuery({
    queryKey: ["github-status"],
    queryFn: getGithubStatus,
  });

  function handleSuccess() {
    void queryClient.invalidateQueries({ queryKey: ["github-status"] });
  }

  async function handleDisconnect() {
    setIsDisconnecting(true);
    try {
      await disconnectGithub();
      void queryClient.invalidateQueries({ queryKey: ["github-status"] });
    } finally {
      setIsDisconnecting(false);
    }
  }

  return (
    <BrutalistCard>
      <p style={{ ...sectionLabel, marginBottom: "var(--frost-line, 16px)" }}>
        § GitHub Integration
      </p>

      <QueryErrorNotification error={statusQuery.error} title="Failed to load GitHub status" />

      {statusQuery.isLoading && !statusQuery.data && (
        <>
          <BrutalistSkeletonText heading width="40%" />
          <BrutalistSkeletonText paragraph lineCount={2} />
        </>
      )}

      {statusQuery.data?.is_connected ? (
        /* Connected state */
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <StatusBadge
              severity={
                statusQuery.data.status === "active"
                  ? "info"
                  : statusQuery.data.status === "needs_reauth"
                  ? "warn"
                  : "alarm"
              }
              title={statusQuery.data.status ?? "unknown"}
            />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: "4px 16px",
              fontFamily: "var(--frost-font-mono)",
              fontSize: "12px",
              fontWeight: 500,
              letterSpacing: "0.4px",
            }}
          >
            <span style={{ color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)" }}>
              Account
            </span>
            <span>{statusQuery.data.github_login ?? "—"}</span>

            <span style={{ color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)" }}>
              Repositories
            </span>
            <span>{statusQuery.data.repo_count}</span>

            {statusQuery.data.last_synced_at && (
              <>
                <span style={{ color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)" }}>
                  Last synced
                </span>
                <span>
                  {new Date(statusQuery.data.last_synced_at).toLocaleString()}
                </span>
              </>
            )}

            <span style={{ color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)" }}>
              Method
            </span>
            <span>
              {statusQuery.data.auth_method === "pat"
                ? "Personal Access Token"
                : "OAuth Device Flow"}
            </span>
          </div>

          <div style={{ marginTop: "8px" }}>
            <BracketButton
              size="sm"
              danger
              isLoading={isDisconnecting}
              onClick={() => void handleDisconnect()}
              aria-label="Disconnect GitHub integration"
            >
              Disconnect
            </BracketButton>
          </div>
        </div>
      ) : statusQuery.data && !statusQuery.data.is_connected ? (
        /* Not connected — show tabs */
        <BracketTabs defaultSelectedIndex={0}>
          <BracketTabList aria-label="GitHub connection method">
            <BracketTab>Personal Access Token</BracketTab>
            <BracketTab>OAuth Device Flow</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>
              <div style={{ paddingTop: "16px" }}>
                <PATPanel onSuccess={handleSuccess} />
              </div>
            </BracketTabPanel>
            <BracketTabPanel>
              <div style={{ paddingTop: "16px" }}>
                <DeviceFlowPanel onSuccess={handleSuccess} />
              </div>
            </BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      ) : null}
    </BrutalistCard>
  );
}

import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { fetchCurrentUser, loginWithTelegram } from "../api/auth";
import { setApiSession } from "../api/session";
import { detectAuthMode } from "./mode";
import { getStoredTokens, setStoredTokens, subscribeTokenChanges } from "./storage";
import type { AuthMode, AuthStatus, AuthTokens, AuthUser, TelegramAuthPayload } from "./types";

interface AuthContextValue {
  mode: AuthMode;
  status: AuthStatus;
  tokens: AuthTokens | null;
  user: AuthUser | null;
  error: string | null;
  login: (payload: TelegramAuthPayload) => Promise<void>;
  logout: () => void;
  reloadUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function getTelegramInitData(): string {
  return window.Telegram?.WebApp?.initData ?? "";
}

export function AuthProvider({ children }: PropsWithChildren) {
  const mode = useMemo(() => detectAuthMode(window), []);
  const [tokens, setTokens] = useState<AuthTokens | null>(() => (mode === "jwt" ? getStoredTokens() : null));
  const [status, setStatus] = useState<AuthStatus>(() => {
    if (mode === "telegram-webapp") return "authenticated";
    return tokens?.accessToken ? "authenticated" : "unauthenticated";
  });
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  const syncApiSession = useCallback(
    (nextTokens: AuthTokens | null) => {
      setApiSession({
        mode,
        accessToken: nextTokens?.accessToken ?? null,
        refreshToken: nextTokens?.refreshToken ?? null,
        initData: mode === "telegram-webapp" ? getTelegramInitData() : "",
      });
    },
    [mode],
  );

  useEffect(() => {
    syncApiSession(tokens);
  }, [tokens, syncApiSession]);

  useEffect(() => {
    if (mode !== "jwt") {
      return;
    }

    return subscribeTokenChanges((nextTokens) => {
      setTokens(nextTokens);
      setStatus(nextTokens?.accessToken ? "authenticated" : "unauthenticated");
      syncApiSession(nextTokens);
    });
  }, [mode, syncApiSession]);

  const reloadUser = useCallback(async () => {
    if (status !== "authenticated") {
      setUser(null);
      return;
    }
    try {
      const current = await fetchCurrentUser();
      setUser(current);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load user profile.";
      setError(message);
      if (mode === "jwt") {
        setStoredTokens(null);
      }
      setStatus(mode === "telegram-webapp" ? "authenticated" : "unauthenticated");
      setUser(null);
    }
  }, [mode, status]);

  useEffect(() => {
    void reloadUser();
  }, [reloadUser]);

  const login = useCallback(async (payload: TelegramAuthPayload) => {
    setStatus("loading");
    setError(null);
    try {
      const nextTokens = await loginWithTelegram(payload);
      setStoredTokens(nextTokens);
      setTokens(nextTokens);
      setStatus("authenticated");
      syncApiSession(nextTokens);
      const current = await fetchCurrentUser();
      setUser(current);
    } catch (err) {
      setStatus("unauthenticated");
      setTokens(null);
      setStoredTokens(null);
      setUser(null);
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      throw err;
    }
  }, [syncApiSession]);

  const logout = useCallback(() => {
    setStoredTokens(null);
    setTokens(null);
    setUser(null);
    setStatus("unauthenticated");
    setError(null);
    syncApiSession(null);
  }, [syncApiSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      mode,
      status,
      tokens,
      user,
      error,
      login,
      logout,
      reloadUser,
    }),
    [error, login, logout, mode, reloadUser, status, tokens, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

import type { AuthMode } from "../auth/types";

export interface ApiSession {
  mode: AuthMode;
  accessToken: string | null;
  refreshToken: string | null;
  initData: string;
}

let session: ApiSession = {
  mode: "jwt",
  accessToken: null,
  refreshToken: null,
  initData: "",
};

export function getApiSession(): ApiSession {
  return session;
}

export function setApiSession(next: ApiSession): void {
  session = next;
}

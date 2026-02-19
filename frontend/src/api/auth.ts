import { apiRequest } from "./client";

export interface CurrentUser {
  user_id: number;
  username: string;
  client_id: string;
  is_owner: boolean;
  created_at: string;
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest("/v1/auth/me");
}

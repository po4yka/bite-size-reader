import { apiRequest } from "./client";

export interface CurrentUser {
  user_id: number;
  username: string;
  client_id: string;
  is_owner: boolean;
  created_at: string;
}

interface CurrentUserBackendResponse {
  userId: number;
  username: string;
  clientId: string;
  isOwner: boolean;
  createdAt: string;
}

export function fetchCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUserBackendResponse>("/v1/auth/me").then((payload) => ({
    user_id: payload.userId,
    username: payload.username,
    client_id: payload.clientId,
    is_owner: payload.isOwner,
    created_at: payload.createdAt,
  }));
}

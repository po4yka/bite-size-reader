import { apiRequest } from "./client";
import type { UserStats } from "../types/api";

export function fetchUserStats(): Promise<UserStats> {
  return apiRequest("/v1/user/stats");
}

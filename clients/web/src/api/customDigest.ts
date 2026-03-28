import { apiRequest } from "./client";

export interface CustomDigestSummary {
  id: number;
  title: string;
  createdAt: string;
  channelCount: number;
  postCount: number;
}

export interface CustomDigestDetail {
  id: number;
  title: string;
  createdAt: string;
  channels: Array<{ id: number; username: string; title: string }>;
  posts: Array<{
    id: number;
    channelId: number;
    text: string;
    createdAt: string;
    relevanceScore: number;
  }>;
}

export interface CreateCustomDigestParams {
  title: string;
  channelIds: number[];
  maxPosts?: number;
  dateFrom?: string;
  dateTo?: string;
}

interface CustomDigestSummaryPayload {
  id?: number;
  title?: string;
  createdAt?: string;
  channelCount?: number;
  postCount?: number;
}

interface ListCustomDigestsPayload {
  digests?: CustomDigestSummaryPayload[];
  total?: number;
  page?: number;
  limit?: number;
}

interface CustomDigestDetailPayload {
  id?: number;
  title?: string;
  createdAt?: string;
  channels?: Array<{ id?: number; username?: string; title?: string }>;
  posts?: Array<{
    id?: number;
    channelId?: number;
    text?: string;
    createdAt?: string;
    relevanceScore?: number;
  }>;
}

function toCustomDigestSummary(p: CustomDigestSummaryPayload): CustomDigestSummary {
  if (p.id == null) throw new Error("Custom digest response is missing id.");
  return {
    id: p.id,
    title: p.title ?? "",
    createdAt: p.createdAt ?? "",
    channelCount: p.channelCount ?? 0,
    postCount: p.postCount ?? 0,
  };
}

export async function createCustomDigest(
  params: CreateCustomDigestParams,
): Promise<CustomDigestSummary> {
  const data = await apiRequest<CustomDigestSummaryPayload>("/v1/digests/custom", {
    method: "POST",
    body: JSON.stringify({
      title: params.title,
      channel_ids: params.channelIds,
      max_posts: params.maxPosts,
      date_from: params.dateFrom,
      date_to: params.dateTo,
    }),
  });
  return toCustomDigestSummary(data);
}

export async function listCustomDigests(
  page = 1,
  limit = 20,
): Promise<{ digests: CustomDigestSummary[]; total: number }> {
  const data = await apiRequest<ListCustomDigestsPayload>(
    `/v1/digests/custom?page=${page}&limit=${limit}`,
  );
  return {
    digests: (data.digests ?? []).map(toCustomDigestSummary),
    total: data.total ?? 0,
  };
}

export async function getCustomDigest(id: number): Promise<CustomDigestDetail> {
  const data = await apiRequest<CustomDigestDetailPayload>(`/v1/digests/custom/${id}`);
  if (data.id == null) throw new Error("Custom digest detail response is missing id.");
  return {
    id: data.id,
    title: data.title ?? "",
    createdAt: data.createdAt ?? "",
    channels: (data.channels ?? []).map((c) => ({
      id: c.id ?? 0,
      username: c.username ?? "",
      title: c.title ?? "",
    })),
    posts: (data.posts ?? []).map((p) => ({
      id: p.id ?? 0,
      channelId: p.channelId ?? 0,
      text: p.text ?? "",
      createdAt: p.createdAt ?? "",
      relevanceScore: p.relevanceScore ?? 0,
    })),
  };
}

import type { PaginationInfo } from "../types/api";

interface BackendPaginationInfo {
  total: number;
  limit: number;
  offset: number;
  hasMore?: boolean;
  has_more?: boolean;
}

export function mapPagination(pagination: BackendPaginationInfo): PaginationInfo {
  return {
    total: pagination.total,
    limit: pagination.limit,
    offset: pagination.offset,
    has_more: Boolean(pagination.hasMore ?? pagination.has_more),
  };
}

export function toDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

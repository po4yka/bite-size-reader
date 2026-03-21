/**
 * Centralised query key registry for TanStack React Query.
 *
 * Critical fix: LibraryPage and ArticlesPage now share the same
 * queryKeys.summaries.list(...) prefix so that any mutation that
 * invalidates queryKeys.summaries.all (["summaries"]) refreshes
 * both pages simultaneously.
 */
export const queryKeys = {
  summaries: {
    all: ["summaries"] as const,
    list: (params: Record<string, unknown>) => ["summaries", "list", params] as const,
    detail: (id: number) => ["summaries", "detail", id] as const,
    content: (id: number) => ["summaries", "content", id] as const,
  },
  tags: {
    all: ["tags"] as const,
    list: () => ["tags", "list"] as const,
  },
  collections: {
    all: ["collections"] as const,
    tree: ["collections", "tree"] as const,
    items: (id: number) => ["collections", "items", id] as const,
  },
  search: {
    results: (params: Record<string, unknown>) => ["search", "results", params] as const,
    trending: ["search", "trending"] as const,
  },
  digest: {
    all: ["digest"] as const,
    channels: ["digest", "channels"] as const,
    categories: ["digest", "categories"] as const,
    preferences: ["digest", "preferences"] as const,
    history: (page: number) => ["digest", "history", page] as const,
    channelPosts: (username: string) => ["digest", "channel-posts", username] as const,
  },
  requests: {
    status: (id: string) => ["requests", "status", id] as const,
    duplicateCheck: (url: string) => ["requests", "duplicate", url] as const,
  },
  user: {
    preferences: ["user", "preferences"] as const,
    stats: ["user", "stats"] as const,
    goals: {
      all: ["user", "goals"] as const,
      progress: ["user", "goals", "progress"] as const,
    },
    streak: ["user", "streak"] as const,
  },
  auth: {
    sessions: ["auth", "sessions"] as const,
    telegramLink: ["auth", "telegram-link"] as const,
  },
  webhooks: {
    all: ["webhooks"] as const,
    list: () => ["webhooks", "list"] as const,
    deliveries: (id: number) => ["webhooks", "deliveries", id] as const,
  },
  rules: {
    all: ["rules"] as const,
    list: () => ["rules", "list"] as const,
    detail: (id: number) => ["rules", "detail", id] as const,
    logs: (id: number) => ["rules", "logs", id] as const,
  },
  importExport: {
    all: ["importExport"] as const,
    jobs: () => ["importExport", "jobs"] as const,
    job: (id: number) => ["importExport", "job", id] as const,
  },
  admin: {
    dbInfo: ["admin", "db-info"] as const,
  },
} as const;

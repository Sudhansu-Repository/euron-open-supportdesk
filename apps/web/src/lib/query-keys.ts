/**
 * Query keys in one place, so invalidation after a mutation (or a live event) names
 * exactly what it touched. Keys are hierarchical: invalidating `qk.tickets` refreshes
 * every list, count and conversation at once.
 */
export const qk = {
  me: ["auth", "session"] as const,
  signupStatus: ["auth", "signup"] as const,
  invitation: (token: string) => ["auth", "invitation", token] as const,

  tickets: ["tickets"] as const,
  ticketLists: ["tickets", "list"] as const,
  ticketList: (filters: object) => ["tickets", "list", filters] as const,
  counts: ["tickets", "counts"] as const,
  ticket: (id: string) => ["tickets", "detail", id] as const,
  macros: ["macros"] as const,
  slaPolicies: ["sla-policies"] as const,

  customers: ["customers"] as const,
  customerList: (filters: object) => ["customers", "list", filters] as const,
  customer: (id: string) => ["customers", "detail", id] as const,

  users: ["users"] as const,
  invitations: ["invitations"] as const,
  teams: ["teams"] as const,
  settings: ["org", "settings"] as const,
  prices: ["org", "prices"] as const,
  inboxes: ["inboxes"] as const,

  knowledge: ["knowledge"] as const,
  knowledgeStats: ["knowledge", "stats"] as const,
  sources: ["knowledge", "sources"] as const,
  chunks: (sourceId: string) => ["knowledge", "chunks", sourceId] as const,
  articles: ["knowledge", "articles"] as const,
  article: (id: string) => ["knowledge", "articles", id] as const,

  gaps: ["gaps"] as const,
  gapList: (status: string) => ["gaps", "list", status] as const,
  gap: (id: string) => ["gaps", "detail", id] as const,

  analytics: ["analytics"] as const,
  overview: (days: number) => ["analytics", "overview", days] as const,
  team: (days: number) => ["analytics", "team", days] as const,
  costs: (days: number) => ["analytics", "costs", days] as const,

  apiKeys: ["api-keys"] as const,
  webhooks: ["webhooks"] as const,
  webhookEvents: ["webhooks", "events"] as const,
  deliveries: (id: string) => ["webhooks", "deliveries", id] as const,
  audit: (action: string) => ["audit", action] as const,

  help: (slug: string) => ["help", slug] as const,
  helpArticles: (slug: string, q: string, category: string) => ["help", slug, "articles", q, category] as const,
  helpArticle: (slug: string, articleSlug: string) => ["help", slug, "article", articleSlug] as const,
  portalTickets: (slug: string) => ["portal", slug, "tickets"] as const,
  portalTicket: (slug: string, id: string) => ["portal", slug, "ticket", id] as const,
  widgetConversation: (id: string) => ["widget", "conversation", id] as const,
};

/** staleTime per kind of data, chosen deliberately. */
export const STALE = {
  live: 5_000,
  list: 15_000,
  config: 30_000,
  static: 5 * 60_000,
} as const;

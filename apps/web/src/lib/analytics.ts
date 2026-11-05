import type { components } from "./api/schema";

/**
 * Analytics types come straight from the API contract (`pnpm gen:api`); only the pure
 * helpers the screen needs on top of them live here. Money arrives as decimal strings.
 */
export type Overview = components["schemas"]["Overview"];
export type Costs = components["schemas"]["Costs"];
export type CostRow = components["schemas"]["CostRow"];
export type Usage = components["schemas"]["Usage"];
export type TeamMember = components["schemas"]["TeamMember"];

/** The breakdown groups the overview sends (`by_channel`, `by_category`, ...), empty when absent. */
export function breakdown(o: Overview, group: string): Record<string, number> {
  return o.breakdown[group] ?? {};
}

/** Cost per AI resolution compared with a per-resolution SaaS price. */
export function savingsVsSaas(costPerResolution: number | null, saasPrice: number): { ratio: number | null; cheaper: boolean } {
  if (costPerResolution == null || saasPrice <= 0) return { ratio: null, cheaper: false };
  if (costPerResolution === 0) return { ratio: null, cheaper: true };
  return { ratio: saasPrice / costPerResolution, cheaper: costPerResolution < saasPrice };
}

/** A count map as rows sorted by size, largest first. */
export function toRows(m: Record<string, number>): { key: string; value: number; share: number }[] {
  const total = Object.values(m).reduce((a, b) => a + b, 0);
  return Object.entries(m)
    .map(([key, value]) => ({ key, value, share: total ? value / total : 0 }))
    .sort((a, b) => b.value - a.value);
}

import { bool, num, obj, str, strs } from "./read";

/**
 * The AI decision stored on each AI message (`message.ai_meta`, written by the API's
 * answer pipeline in ai/engine.py). The contract types it as a free-form object, so this
 * is the one place that reads it.
 */
export interface AiDecision {
  action: string | null;
  reasons: string[];
  method: string | null;
  grounded: boolean;
  triage: {
    intent: string | null;
    category: string | null;
    sentiment: string | null;
    priority: string | null;
    sensitive: string[];
    source: string | null;
  } | null;
  bestRelevance: number | null;
  cache: string | null;
  tokens: number;
  costUsd: number;
  timings: { step: string; ms: number }[];
  providerError: string | null;
  handoff: boolean;
  approvedBy: string | null;
  editedBy: string | null;
}

export function readAiMeta(raw: unknown): AiDecision {
  const m = obj(raw);
  const t = m.triage === undefined ? null : obj(m.triage);
  const timings = Object.entries(obj(m.timings_ms))
    .map(([step, v]) => ({ step, ms: num(v) ?? 0 }))
    .filter((x) => x.ms >= 0);
  return {
    action: str(m.action),
    reasons: strs(m.reasons),
    method: str(m.method),
    grounded: bool(m.grounded),
    triage: t
      ? {
          intent: str(t.intent),
          category: str(t.category),
          sentiment: str(t.sentiment),
          priority: str(t.priority),
          sensitive: strs(t.sensitive),
          source: str(t.source),
        }
      : null,
    bestRelevance: num(m.best_relevance),
    cache: str(m.cache),
    tokens: num(m.tokens) ?? 0,
    costUsd: num(m.cost_usd) ?? 0,
    timings,
    providerError: str(m.provider_error),
    handoff: bool(m.handoff),
    approvedBy: str(m.approved_by),
    editedBy: str(m.edited_by),
  };
}

/** Whether a decision has anything worth showing in the decision panel. */
export function hasDecision(d: AiDecision): boolean {
  return d.action != null || d.triage != null || d.tokens > 0;
}

/** "Answer cache (semantic)" style method line, cache taking precedence. */
export function answerSource(d: AiDecision): string {
  if (d.cache) return d.cache;
  return d.method ?? "none";
}

/** Timing step names as people read them. */
export function stepLabel(step: string): string {
  const map: Record<string, string> = {
    triage: "Triage",
    retrieve: "Retrieval",
    retrieval: "Retrieval",
    embed: "Embedding",
    cache: "Cache lookup",
    answer: "Answer",
    generate: "Generation",
    total: "Total",
  };
  return map[step] ?? step.charAt(0).toUpperCase() + step.slice(1).replace(/_/g, " ");
}

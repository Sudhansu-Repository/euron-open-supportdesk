import { describe, expect, it } from "vitest";

import { answerSource, hasDecision, readAiMeta, stepLabel } from "@/lib/ai-meta";
import { breakdown, savingsVsSaas, toRows, type Overview } from "@/lib/analytics";

describe("AI decision (message.ai_meta)", () => {
  it("reads what the answer pipeline stores", () => {
    const d = readAiMeta({
      action: "approval",
      reasons: ["sensitive_intent"],
      method: "model",
      grounded: true,
      triage: { intent: "refund", category: "billing", sentiment: "negative", priority: "high", sensitive: ["refund"], source: "rules" },
      best_relevance: 0.734,
      cache: null,
      tokens: 812,
      cost_usd: "0.000412",
      timings_ms: { triage: 1.2, retrieve: 14.5, generate: 820 },
      provider_error: null,
    });
    expect(d.action).toBe("approval");
    expect(d.triage?.sensitive).toEqual(["refund"]);
    expect(d.costUsd).toBeCloseTo(0.000412);
    expect(d.timings.map((t) => t.step)).toEqual(["triage", "retrieve", "generate"]);
    expect(hasDecision(d)).toBe(true);
    expect(answerSource(d)).toBe("model");
  });
  it("survives empty and malformed metadata", () => {
    const d = readAiMeta({ reasons: "nope", tokens: "x", triage: 5 });
    expect(d.reasons).toEqual([]);
    expect(d.tokens).toBe(0);
    expect(d.triage).toEqual({ intent: null, category: null, sentiment: null, priority: null, sensitive: [], source: null });
    expect(hasDecision(readAiMeta({}))).toBe(false);
    expect(readAiMeta({ handoff: true, reasons: ["ai_unavailable"] }).handoff).toBe(true);
  });
  it("prefers the cache kind as the answer source and labels steps", () => {
    expect(answerSource(readAiMeta({ cache: "semantic", method: "model" }))).toBe("semantic");
    expect(stepLabel("retrieve")).toBe("Retrieval");
    expect(stepLabel("rerank_x")).toBe("Rerank x");
  });
});

describe("analytics helpers", () => {
  it("reads breakdown groups from the typed overview, empty when absent", () => {
    const o = { breakdown: { by_channel: { widget: 7, email: 3 } } } as unknown as Overview;
    expect(breakdown(o, "by_channel")).toEqual({ widget: 7, email: 3 });
    expect(breakdown(o, "sentiment")).toEqual({});
  });
  it("compares the cost per AI resolution with the SaaS price honestly", () => {
    const r = savingsVsSaas(0.0099, 0.99);
    expect(r.cheaper).toBe(true);
    expect(r.ratio).toBeCloseTo(100);
    expect(savingsVsSaas(2, 0.99).cheaper).toBe(false);
    expect(savingsVsSaas(null, 0.99)).toEqual({ ratio: null, cheaper: false });
    expect(savingsVsSaas(0, 0.99)).toEqual({ ratio: null, cheaper: true });
  });
  it("sorts breakdowns by size with shares", () => {
    expect(toRows({ a: 1, b: 3 })).toEqual([
      { key: "b", value: 3, share: 0.75 },
      { key: "a", value: 1, share: 0.25 },
    ]);
    expect(toRows({})).toEqual([]);
  });
});

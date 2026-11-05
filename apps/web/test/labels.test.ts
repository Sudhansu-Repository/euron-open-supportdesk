import { describe, expect, it } from "vitest";

import { actionSpec, eventLabel, humanize, intentLabel, methodLabel, prioritySpec, reasonLabel, reasonSpec, REASONS, statusSpec } from "@/lib/labels";

describe("reason codes", () => {
  it("has a human label and an explanation for every code the API's policy engine emits", () => {
    const apiCodes = [
      "customer_requested",
      "sensitive_intent",
      "negative_sentiment",
      "vip_customer",
      "category_not_allowed",
      "no_grounded_answer",
      "answer_unhelpful",
      "max_ai_turns",
      "ai_off",
      "ai_unavailable",
      "budget_exhausted",
      "sensitive_answer",
    ];
    for (const code of apiCodes) {
      expect(REASONS[code]?.label).toBeTruthy();
      expect(REASONS[code]?.explain.length).toBeGreaterThan(20);
    }
    expect(reasonLabel("no_grounded_answer")).toBe("Not covered by the knowledge base");
    expect(reasonLabel("customer_requested")).toBe("Customer asked for a person");
    expect(reasonLabel("sensitive_answer")).toBe("AI answer mentioned a sensitive action");
  });
  it("never shows a blank for an unknown code", () => {
    expect(reasonSpec("brand_new_rule").label).toBe("Brand new rule");
    expect(reasonSpec("brand_new_rule").tone).toBe("neutral");
  });
});

describe("other codes", () => {
  it("humanizes snake, dot and dash codes", () => {
    expect(humanize("billing_dispute")).toBe("Billing dispute");
    expect(humanize("ai.answered")).toBe("Ai answered");
    expect(humanize("")).toBe("");
    expect(humanize(null)).toBe("");
  });
  it("labels policy actions and methods", () => {
    expect(actionSpec("send").tone).toBe("success");
    expect(actionSpec("approval").label).toBe("Held for approval");
    expect(actionSpec(null).label).toBe("Unknown");
    expect(methodLabel("extractive")).toBe("Extractive");
    expect(methodLabel("semantic")).toBe("Semantic cache");
    expect(methodLabel(null)).toBe("None");
  });
  it("labels statuses, priorities and intents", () => {
    expect(statusSpec("pending").label).toBe("Pending");
    expect(prioritySpec("urgent").rank).toBe(3);
    expect(prioritySpec("weird").label).toBe("Weird");
    expect(intentLabel("account_change")).toBe("Account change");
    expect(intentLabel("human")).toBe("Wants a person");
    expect(intentLabel(null)).toBe("Unknown");
  });
  it("tells the conversation history in sentences", () => {
    expect(eventLabel("status", { before: "open", after: "resolved" })).toBe("Status set to resolved");
    expect(eventLabel("escalated", { reasons: ["vip_customer", "sensitive_intent"] })).toBe("Escalated: VIP customer, Sensitive request");
    expect(eventLabel("rated", { score: 4 })).toBe("Customer rated 4 of 5");
    expect(eventLabel("ai.answered", { method: "extractive", cache: null })).toBe("AI answered (Extractive)");
    expect(eventLabel("ai.answered", { cache: "semantic" })).toBe("AI answered from the semantic cache");
    expect(eventLabel("assigned", { assignee_id: "x" })).toBe("Assigned");
    expect(eventLabel("something_new", {})).toBe("Something new");
  });
});

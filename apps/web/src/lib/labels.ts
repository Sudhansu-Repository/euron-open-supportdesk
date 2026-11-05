/**
 * Human words for every code the API sends: escalation reasons, AI actions and methods,
 * statuses, priorities, channels, intents and sentiment. Unknown codes degrade to a
 * readable version of the code itself, never to a blank.
 */

export type Tone = "success" | "info" | "primary" | "warning" | "danger" | "neutral" | "ai";

/** "billing_dispute" becomes "Billing dispute". */
export function humanize(code: string | null | undefined): string {
  if (!code) return "";
  const words = code.replace(/[._-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "";
}

export interface ReasonSpec {
  label: string;
  /** One sentence an agent reads to understand why the AI stepped back. */
  explain: string;
  tone: Tone;
}

/** Mirrors the reason codes of the API's escalation engine (ai/policy.py). */
export const REASONS: Record<string, ReasonSpec> = {
  customer_requested: {
    label: "Customer asked for a person",
    explain: "The customer asked to talk to a human, so the AI handed over at once.",
    tone: "info",
  },
  sensitive_intent: {
    label: "Sensitive request",
    explain: "Refunds, cancellations, account changes, legal, security and data deletion always involve a person.",
    tone: "warning",
  },
  negative_sentiment: {
    label: "Customer is frustrated",
    explain: "Triage read the message as negative, and your policy sends frustrated customers to a person.",
    tone: "danger",
  },
  vip_customer: {
    label: "VIP customer",
    explain: "This customer is marked VIP, and your policy gives VIPs a person.",
    tone: "primary",
  },
  category_not_allowed: {
    label: "Category needs a person",
    explain: "The AI may only resolve the categories you allowed in Policy; this one is not on the list.",
    tone: "neutral",
  },
  no_grounded_answer: {
    label: "Not covered by the knowledge base",
    explain: "No passage scored above the relevance threshold, so the AI did not guess. A knowledge gap was recorded.",
    tone: "warning",
  },
  answer_unhelpful: {
    label: "AI answer did not help",
    explain: "The customer said earlier answers did not help.",
    tone: "danger",
  },
  max_ai_turns: {
    label: "Long AI conversation",
    explain: "The conversation reached the maximum number of AI turns set in Policy.",
    tone: "neutral",
  },
  ai_off: {
    label: "AI is off",
    explain: "AI answers are switched off for this organisation or inbox.",
    tone: "neutral",
  },
  ai_unavailable: {
    label: "AI provider unavailable",
    explain: "The model did not answer in time or returned an error, so a person takes over. No message was lost.",
    tone: "danger",
  },
  sensitive_answer: {
    label: "AI answer mentioned a sensitive action",
    explain: "The drafted answer itself mentions a sensitive action (a refund, a cancellation, an account change), so a person checks it before it reaches the customer.",
    tone: "warning",
  },
  budget_exhausted: {
    label: "AI budget spent",
    explain: "The daily or monthly token or cost budget is used up, and Budgets says to hand over to a person.",
    tone: "warning",
  },
};

export function reasonSpec(code: string): ReasonSpec {
  return REASONS[code] ?? { label: humanize(code), explain: "A rule in your policy asked for a person.", tone: "neutral" };
}

export function reasonLabel(code: string): string {
  return reasonSpec(code).label;
}

export interface ActionSpec {
  label: string;
  explain: string;
  tone: Tone;
}

/** What the policy decided to do with an AI answer. */
export const ACTIONS: Record<string, ActionSpec> = {
  send: { label: "Sent to the customer", explain: "Grounded in your knowledge and allowed by your policy.", tone: "success" },
  approval: { label: "Held for approval", explain: "A sensitive request in approval mode: a person approves before it is sent.", tone: "warning" },
  draft: { label: "Kept as a draft", explain: "Your policy lets the AI prepare this answer, and a person decides.", tone: "info" },
  escalate: { label: "Handed to a person", explain: "The AI did not answer; the conversation went to your team.", tone: "danger" },
};

/** The same decision, phrased for the playground, where nothing is actually sent. */
export const WOULD: Record<string, string> = {
  send: "Would be sent",
  approval: "Would wait for approval",
  draft: "Would be a draft for an agent",
  escalate: "Would go to a person",
};

export function actionSpec(code: string | null | undefined): ActionSpec {
  return (code && ACTIONS[code]) || { label: humanize(code) || "Unknown", explain: "", tone: "neutral" };
}

/** How an answer was produced. */
export const METHODS: Record<string, { label: string; explain: string }> = {
  model: { label: "Language model", explain: "Written by your configured model from the retrieved passages." },
  extractive: { label: "Extractive", explain: "The best passage of your docs, quoted as is. No model, no tokens." },
  cache: { label: "Answer cache", explain: "Reused from an earlier answer to the same question. Zero tokens." },
  exact: { label: "Exact cache", explain: "The same question was answered before with the same knowledge. Zero tokens." },
  semantic: { label: "Semantic cache", explain: "A question with the same meaning was answered before. Zero tokens." },
};

export function methodLabel(code: string | null | undefined): string {
  if (!code) return "None";
  return METHODS[code]?.label ?? humanize(code);
}

export const STATUS: Record<string, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "primary" },
  pending: { label: "Pending", tone: "warning" },
  resolved: { label: "Resolved", tone: "success" },
  closed: { label: "Closed", tone: "neutral" },
};

export function statusSpec(code: string): { label: string; tone: Tone } {
  return STATUS[code] ?? { label: humanize(code), tone: "neutral" };
}

export const STATUS_HINT: Record<string, string> = {
  open: "Needs a reply from your team or the AI.",
  pending: "Waiting on the customer.",
  resolved: "Done. Reopens if the customer writes again.",
  closed: "Archived. A new message starts a new conversation.",
};

export const PRIORITIES = ["low", "normal", "high", "urgent"] as const;

export const PRIORITY: Record<string, { label: string; tone: Tone; rank: number }> = {
  low: { label: "Low", tone: "neutral", rank: 0 },
  normal: { label: "Normal", tone: "neutral", rank: 1 },
  high: { label: "High", tone: "warning", rank: 2 },
  urgent: { label: "Urgent", tone: "danger", rank: 3 },
};

export function prioritySpec(code: string): { label: string; tone: Tone; rank: number } {
  return PRIORITY[code] ?? { label: humanize(code), tone: "neutral", rank: 1 };
}

export const CHANNELS: Record<string, string> = {
  widget: "Website chat",
  email: "Email",
  portal: "Customer portal",
  api: "API",
};

export function channelLabel(code: string): string {
  return CHANNELS[code] ?? humanize(code);
}

export const SENTIMENT: Record<string, { label: string; tone: Tone }> = {
  positive: { label: "Positive", tone: "success" },
  neutral: { label: "Neutral", tone: "neutral" },
  negative: { label: "Negative", tone: "danger" },
};

export function sentimentSpec(code: string | null | undefined): { label: string; tone: Tone } {
  if (!code) return { label: "Unknown", tone: "neutral" };
  return SENTIMENT[code] ?? { label: humanize(code), tone: "neutral" };
}

/** Sensitive intents the policy can hold for a person (ai/triage.py). */
export const SENSITIVE_INTENTS: { value: string; label: string }[] = [
  { value: "refund", label: "Refund" },
  { value: "cancellation", label: "Cancellation" },
  { value: "account_change", label: "Account change" },
  { value: "billing_dispute", label: "Billing dispute" },
  { value: "legal", label: "Legal" },
  { value: "security", label: "Security" },
  { value: "data_deletion", label: "Data deletion" },
];

export function intentLabel(code: string | null | undefined): string {
  if (!code) return "Unknown";
  if (code === "question") return "Question";
  if (code === "human") return "Wants a person";
  if (code === "custom") return "Custom keyword";
  return SENSITIVE_INTENTS.find((i) => i.value === code)?.label ?? humanize(code);
}

export const POLICY_MODES: { value: "off" | "draft" | "approval" | "auto"; label: string; explain: string }[] = [
  { value: "off", label: "Off", explain: "The AI never answers. Every conversation goes straight to your team." },
  {
    value: "draft",
    label: "Draft only",
    explain: "The AI writes a grounded draft for every question, and an agent sends it. Nothing reaches a customer unseen.",
  },
  {
    value: "approval",
    label: "Auto, with approval",
    explain:
      "The AI answers grounded questions in your allowed categories. Sensitive requests wait for an agent to approve the answer.",
  },
  {
    value: "auto",
    label: "Full auto",
    explain: "The AI answers grounded questions in your allowed categories. Sensitive requests still go to a person with a draft.",
  },
];

/** Ticket history events (tickets/service.py) in a sentence. */
export function eventLabel(type: string, data: Record<string, unknown>): string {
  switch (type) {
    case "created":
      return "Conversation started";
    case "reopened":
      return "Reopened by a new message";
    case "taken_over":
      return "Taken over by an agent";
    case "assigned":
      return data.assignee_name ? `Assigned to ${String(data.assignee_name)}` : data.assignee_id ? "Assigned" : "Unassigned";
    case "note":
      return "Internal note added";
    case "status":
      return data.after ? `Status set to ${statusSpec(String(data.after)).label.toLowerCase()}` : "Status changed";
    case "escalated": {
      const reasons = Array.isArray(data.reasons) ? (data.reasons as unknown[]).map((r) => reasonLabel(String(r))) : [];
      return reasons.length ? `Escalated: ${reasons.join(", ")}` : "Escalated to a person";
    }
    case "approved":
      return "AI answer approved and sent";
    case "rejected":
      return "AI answer discarded";
    case "rated":
      return data.score != null ? `Customer rated ${String(data.score)} of 5` : "Customer left a rating";
    case "ai.answered":
      return data.cache ? `AI answered from the ${String(data.cache)} cache` : `AI answered (${methodLabel(data.method as string)})`;
    case "ai.decision":
      return `AI decision: ${actionSpec(data.action as string).label.toLowerCase()}`;
    default:
      return humanize(type);
  }
}

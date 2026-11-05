import type { TicketView, ViewCounts } from "@/lib/api/types";

/**
 * The saved views of the inbox, in the order agents work them. `count` reads the
 * matching field of GET /tickets/counts (Resolved has no count).
 */
export interface ViewSpec {
  id: TicketView;
  label: string;
  hint: string;
  count?: keyof ViewCounts;
  empty: { title: string; body: string };
}

export const VIEWS: ViewSpec[] = [
  {
    id: "all",
    label: "All open",
    hint: "Every open or pending conversation.",
    count: "all",
    empty: { title: "Inbox zero", body: "No open conversations. New questions from the widget, email and the portal land here." },
  },
  {
    id: "mine",
    label: "Mine",
    hint: "Assigned to you.",
    count: "mine",
    empty: { title: "Nothing assigned to you", body: "Conversations assigned to you appear here. Pick one up from Unassigned." },
  },
  {
    id: "unassigned",
    label: "Unassigned",
    hint: "Handed to the team, no owner yet.",
    count: "unassigned",
    empty: { title: "Everything has an owner", body: "Escalated conversations wait here when no online agent has capacity." },
  },
  {
    id: "ai",
    label: "AI handling",
    hint: "The AI agent is on it.",
    count: "ai",
    empty: { title: "The AI is not handling anything", body: "Conversations the AI is answering show here, so you can watch or take over." },
  },
  {
    id: "approvals",
    label: "Needs approval",
    hint: "AI answers waiting for a person.",
    count: "approvals",
    empty: { title: "No answers waiting", body: "Sensitive requests in approval mode wait here until an agent approves the AI answer." },
  },
  {
    id: "escalated",
    label: "Escalated",
    hint: "Handed over by the AI, with a reason.",
    count: "escalated",
    empty: { title: "No escalations", body: "When the AI hands a conversation to a person, it lands here with the reason and a summary." },
  },
  {
    id: "sla",
    label: "SLA at risk",
    hint: "Close to or past the response target.",
    count: "sla",
    empty: { title: "Every SLA is on track", body: "Conversations close to or past their response or resolution target show here." },
  },
  {
    id: "resolved",
    label: "Resolved",
    hint: "Done, by the AI or your team.",
    empty: { title: "Nothing resolved yet", body: "Resolved conversations, by the AI or by your team, are kept here." },
  },
];

export function viewSpec(id: string | null | undefined): ViewSpec {
  return VIEWS.find((v) => v.id === id) ?? (VIEWS[0] as ViewSpec);
}

/** "#123" or "123" means "conversation number 123"; anything else is full text. */
export function parseSearch(q: string): { kind: "number"; value: number } | { kind: "text"; value: string } | null {
  const t = q.trim();
  if (!t) return null;
  const m = /^#?(\d{1,9})$/.exec(t);
  if (m) return { kind: "number", value: Number(m[1]) };
  return { kind: "text", value: t };
}

/** The next or previous id in a list for j/k navigation; stays put at the ends. */
export function stepSelection(ids: string[], current: string | null, delta: 1 | -1): string | null {
  if (!ids.length) return null;
  if (!current) return ids[0] ?? null;
  const i = ids.indexOf(current);
  if (i === -1) return ids[0] ?? null;
  const j = Math.min(ids.length - 1, Math.max(0, i + delta));
  return ids[j] ?? null;
}

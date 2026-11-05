import type { PublicMessage, WidgetConfig, WidgetConversation } from "@/lib/api/types";

/**
 * The website widget's local state. Server data (the conversation) comes from React
 * Query; this reducer holds what only the visitor's browser knows: the session, what they
 * rated, which answers they voted on, whether they left an email. Pure, so every
 * transition is unit tested.
 */
export interface WidgetState {
  phase: "loading" | "ready" | "error";
  error: string | null;
  token: string | null;
  config: WidgetConfig | null;
  customerName: string | null;
  ticketId: string | null;
  votes: Record<string, boolean>;
  rated: boolean;
  emailSent: boolean;
  humanRequested: boolean;
}

export type WidgetAction =
  | { type: "session"; token: string; config: WidgetConfig; ticketId: string | null; customerName: string | null }
  | { type: "failed"; error: string }
  | { type: "conversation"; ticketId: string }
  | { type: "vote"; messageId: string; helpful: boolean }
  | { type: "human" }
  | { type: "rated" }
  | { type: "emailSent" }
  | { type: "newConversation" };

export const initialWidgetState: WidgetState = {
  phase: "loading",
  error: null,
  token: null,
  config: null,
  customerName: null,
  ticketId: null,
  votes: {},
  rated: false,
  emailSent: false,
  humanRequested: false,
};

export function widgetReducer(state: WidgetState, action: WidgetAction): WidgetState {
  switch (action.type) {
    case "session":
      return { ...state, phase: "ready", error: null, token: action.token, config: action.config, ticketId: action.ticketId, customerName: action.customerName };
    case "failed":
      return { ...state, phase: "error", error: action.error };
    case "conversation":
      return state.ticketId === action.ticketId ? state : { ...state, ticketId: action.ticketId, rated: false, humanRequested: false };
    case "vote":
      return { ...state, votes: { ...state.votes, [action.messageId]: action.helpful } };
    case "human":
      return { ...state, humanRequested: true };
    case "rated":
      return { ...state, rated: true };
    case "emailSent":
      return { ...state, emailSent: true };
    case "newConversation":
      return { ...state, ticketId: null, votes: {}, rated: false, emailSent: false, humanRequested: false };
    default:
      return state;
  }
}

/** The customer-visible replies; the API whitelists them, so nothing else ever arrives. */
export function visibleMessages(c: WidgetConversation | null | undefined): PublicMessage[] {
  return c?.messages ?? [];
}

/** The AI is working when the customer spoke last and the AI still handles the conversation. */
export function aiTyping(c: WidgetConversation | null | undefined): boolean {
  if (!c || c.handled_by !== "ai") return false;
  if (c.status === "resolved" || c.status === "closed") return false;
  const last = visibleMessages(c).at(-1);
  return last?.author_type === "customer";
}

/** Waiting on someone: worth polling when the live socket is down. */
export function waiting(c: WidgetConversation | null | undefined): boolean {
  if (!c) return false;
  if (aiTyping(c)) return true;
  return c.handled_by !== "ai" && (c.status === "open" || c.status === "pending");
}

/** Offer "email me" when a person must answer and nobody is online, unless already left. */
export function showEmailForm(c: WidgetConversation | null | undefined, state: Pick<WidgetState, "emailSent">): boolean {
  if (!c || state.emailSent) return false;
  return c.handled_by !== "ai" && !c.agents_online && c.status !== "resolved" && c.status !== "closed";
}

/** Ask for a rating once the conversation is resolved. */
export function showRating(c: WidgetConversation | null | undefined, state: Pick<WidgetState, "rated">): boolean {
  return !!c && !state.rated && (c.status === "resolved" || c.status === "closed");
}

/** "Talk to a person" while the AI handles the conversation. */
export function canAskHuman(c: WidgetConversation | null | undefined, state: Pick<WidgetState, "humanRequested">): boolean {
  return !!c && c.handled_by === "ai" && !state.humanRequested && c.status !== "closed";
}

/**
 * Black or white text on the brand colour, whichever has more contrast (WCAG relative
 * luminance). Falls back to white for anything that is not a #rrggbb colour.
 */
export function readableOn(hex: string): "#ffffff" | "#0b0b1a" {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m || !m[1]) return "#ffffff";
  const n = parseInt(m[1], 16);
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const L = 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
  const whiteContrast = 1.05 / (L + 0.05);
  const blackContrast = (L + 0.05) / 0.05;
  return whiteContrast >= blackContrast ? "#ffffff" : "#0b0b1a";
}

/** A brand colour the widget can trust, or the default indigo. */
export function safeColor(color: string | null | undefined): string {
  return color && /^#[0-9a-f]{6}$/i.test(color.trim()) ? color.trim() : "#4f46e5";
}

export const TOKEN_PREFIX = "supportdesk.widget.";

/**
 * A signed-in customer, as the host page passes it to the widget (script tag attributes or
 * `SupportDesk.identify`). The API verifies `userHash` (HMAC-SHA256 of the user id with the
 * inbox's identity secret); the browser only carries it.
 */
export interface WidgetIdentity {
  userId: string;
  userHash: string | null;
  email: string | null;
  name: string | null;
}

function clean(v: unknown, max: number): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  return t && t.length <= max ? t : null;
}

/** Validate what the loader sent; anything unusable means "anonymous visitor". */
export function readIdentity(raw: unknown): WidgetIdentity | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const userId = clean(r.externalId, 200) ?? clean(r.userId, 200);
  if (!userId) return null;
  const hash = clean(r.signature, 128) ?? clean(r.userHash, 128);
  const email = clean(r.email, 254);
  return {
    userId,
    userHash: hash && /^[0-9a-f]+$/i.test(hash) ? hash.toLowerCase() : null,
    email: email && /^[^\s@]+@[^\s@]+$/.test(email) ? email : null,
    name: clean(r.name, 200),
  };
}

/** The session request fields for an identity (the API's names). */
export function identityFields(i: WidgetIdentity | null): { external_id: string | null; signature: string | null; email: string | null; name: string | null } {
  return { external_id: i?.userId ?? null, signature: i?.userHash ?? null, email: i?.email ?? null, name: i?.name ?? null };
}

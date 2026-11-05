import { describe, expect, it } from "vitest";

import {
  aiTyping,
  canAskHuman,
  initialWidgetState,
  readableOn,
  safeColor,
  showEmailForm,
  showRating,
  visibleMessages,
  waiting,
  widgetReducer,
} from "@/features/widget/state";
import type { PublicMessage, WidgetConfig, WidgetConversation } from "@/lib/api/types";

const config: WidgetConfig = {
  title: "Support",
  greeting: "Hi",
  color: "#4f46e5",
  position: "right",
  suggestions: [],
  launcher_label: "Help",
  company: "Acme",
  agents_online: true,
  ai_enabled: true,
};

function msg(author: string, extra: Partial<PublicMessage> = {}): PublicMessage {
  return { id: Math.random().toString(36), author_type: author, body: "x", citations: [], feedback: null, created_at: "2026-10-30T10:00:00Z", ...extra };
}

function conv(extra: Partial<WidgetConversation> = {}): WidgetConversation {
  return { ticket_id: "t1", number: 1, status: "open", handled_by: "ai", agents_online: true, messages: [], ...extra };
}

describe("widget reducer", () => {
  it("starts loading, then holds the session", () => {
    const s = widgetReducer(initialWidgetState, { type: "session", token: "tok", config, ticketId: "t1", customerName: "Visitor" });
    expect(s).toMatchObject({ phase: "ready", token: "tok", ticketId: "t1", customerName: "Visitor" });
    expect(widgetReducer(s, { type: "failed", error: "nope" })).toMatchObject({ phase: "error", error: "nope" });
  });
  it("switches conversation and resets per-conversation flags", () => {
    let s = widgetReducer(initialWidgetState, { type: "session", token: "tok", config, ticketId: null, customerName: null });
    s = widgetReducer(s, { type: "rated" });
    s = widgetReducer(s, { type: "conversation", ticketId: "t2" });
    expect(s.ticketId).toBe("t2");
    expect(s.rated).toBe(false);
    expect(widgetReducer(s, { type: "conversation", ticketId: "t2" })).toBe(s);
  });
  it("records votes, handoff, rating and email, and starts over", () => {
    let s = widgetReducer(initialWidgetState, { type: "vote", messageId: "m1", helpful: false });
    s = widgetReducer(s, { type: "human" });
    s = widgetReducer(s, { type: "emailSent" });
    expect(s).toMatchObject({ votes: { m1: false }, humanRequested: true, emailSent: true });
    s = widgetReducer({ ...s, ticketId: "t1" }, { type: "newConversation" });
    expect(s).toMatchObject({ ticketId: null, votes: {}, humanRequested: false, emailSent: false, rated: false });
  });
});

describe("widget derived state", () => {
  it("shows typing while the AI owes an answer", () => {
    expect(aiTyping(conv({ messages: [msg("customer")] }))).toBe(true);
    expect(aiTyping(conv({ messages: [msg("customer"), msg("ai")] }))).toBe(false);
    expect(aiTyping(conv({ handled_by: "human", messages: [msg("customer")] }))).toBe(false);
    expect(aiTyping(conv({ status: "resolved", messages: [msg("customer")] }))).toBe(false);
    expect(aiTyping(null)).toBe(false);
  });
  it("shows exactly the customer-visible replies the API sends", () => {
    expect(visibleMessages(conv({ messages: [msg("customer"), msg("ai")] }))).toHaveLength(2);
    expect(visibleMessages(null)).toEqual([]);
  });
  it("polls while waiting on the AI or a person", () => {
    expect(waiting(conv({ messages: [msg("customer")] }))).toBe(true);
    expect(waiting(conv({ handled_by: "human", status: "open" }))).toBe(true);
    expect(waiting(conv({ messages: [msg("customer"), msg("ai")], status: "pending" }))).toBe(false);
    expect(waiting(null)).toBe(false);
  });
  it("offers email only when a person must answer and nobody is online", () => {
    const offline = conv({ handled_by: "human", agents_online: false });
    expect(showEmailForm(offline, { emailSent: false })).toBe(true);
    expect(showEmailForm(offline, { emailSent: true })).toBe(false);
    expect(showEmailForm(conv({ handled_by: "human", agents_online: true }), { emailSent: false })).toBe(false);
    expect(showEmailForm(conv({ agents_online: false }), { emailSent: false })).toBe(false);
  });
  it("asks for a rating after resolution, once", () => {
    expect(showRating(conv({ status: "resolved" }), { rated: false })).toBe(true);
    expect(showRating(conv({ status: "resolved" }), { rated: true })).toBe(false);
    expect(showRating(conv({ status: "open" }), { rated: false })).toBe(false);
  });
  it("offers a person while the AI handles it", () => {
    expect(canAskHuman(conv(), { humanRequested: false })).toBe(true);
    expect(canAskHuman(conv(), { humanRequested: true })).toBe(false);
    expect(canAskHuman(conv({ handled_by: "human" }), { humanRequested: false })).toBe(false);
  });
});

describe("brand colour", () => {
  it("picks readable text on the brand colour", () => {
    expect(readableOn("#4f46e5")).toBe("#ffffff");
    expect(readableOn("#facc15")).toBe("#0b0b1a");
    expect(readableOn("#ffffff")).toBe("#0b0b1a");
    expect(readableOn("nope")).toBe("#ffffff");
  });
  it("only trusts #rrggbb colours", () => {
    expect(safeColor("#10B981")).toBe("#10B981");
    expect(safeColor("red; background:url(x)")).toBe("#4f46e5");
    expect(safeColor(null)).toBe("#4f46e5");
  });
});

describe("widget identity", () => {
  it("reads a signed-in customer from the loader and maps it to the session fields", async () => {
    const { readIdentity, identityFields } = await import("@/features/widget/state");
    const i = readIdentity({ userId: " 42 ", userHash: "ABCdef0123", email: "ana@example.com", name: "Ana" });
    expect(i).toEqual({ userId: "42", userHash: "abcdef0123", email: "ana@example.com", name: "Ana" });
    expect(identityFields(i)).toEqual({ external_id: "42", signature: "abcdef0123", email: "ana@example.com", name: "Ana" });
    expect(readIdentity({ externalId: "9", signature: "ff00" })).toEqual({ userId: "9", userHash: "ff00", email: null, name: null });
    expect(identityFields(null)).toEqual({ external_id: null, signature: null, email: null, name: null });
  });
  it("treats anything unusable as an anonymous visitor", async () => {
    const { readIdentity } = await import("@/features/widget/state");
    expect(readIdentity(null)).toBeNull();
    expect(readIdentity({ userHash: "abc" })).toBeNull();
    expect(readIdentity({ userId: "x".repeat(300) })).toBeNull();
    expect(readIdentity({ userId: "7", userHash: "not hex!", email: "nope" })).toEqual({ userId: "7", userHash: null, email: null, name: null });
  });
});

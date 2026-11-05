import { describe, expect, it } from "vitest";

import { agentKeysFor, customerShouldRefetch, parseLiveEvent, reconnectDelay, socketUrl } from "@/lib/live-events";
import { qk } from "@/lib/query-keys";

describe("live event parsing", () => {
  it("accepts small JSON objects with a type", () => {
    expect(parseLiveEvent('{"type":"message.created","ticket_id":"t1"}')).toEqual({ type: "message.created", ticket_id: "t1" });
    expect(parseLiveEvent('{"type":"typing","who":"customer","ticket_id":"t1","extra":1}')).toEqual({ type: "typing", who: "customer", ticket_id: "t1" });
  });
  it("ignores anything else", () => {
    expect(parseLiveEvent("not json")).toBeNull();
    expect(parseLiveEvent("[1,2]")).toBeNull();
    expect(parseLiveEvent('{"kind":"x"}')).toBeNull();
    expect(parseLiveEvent(42)).toBeNull();
    expect(parseLiveEvent(`{"type":"${"x".repeat(5000)}"}`)).toBeNull();
  });
});

describe("agent invalidations", () => {
  it("refreshes lists, counts and the named conversation on a new message", () => {
    expect(agentKeysFor({ type: "message.created", ticket_id: "t1" })).toEqual([qk.ticketLists, qk.counts, qk.ticket("t1")]);
    expect(agentKeysFor({ type: "ticket.updated", ticket_id: "t9" })).toContainEqual(qk.ticket("t9"));
  });
  it("refreshes only lists when no conversation is named", () => {
    expect(agentKeysFor({ type: "ticket.updated" })).toEqual([qk.ticketLists, qk.counts]);
  });
  it("refreshes people on presence and nothing on pings", () => {
    expect(agentKeysFor({ type: "presence", user_id: "u" })).toEqual([qk.users, qk.me]);
    expect(agentKeysFor({ type: "ping" })).toEqual([]);
    expect(agentKeysFor({ type: "ready" })).toEqual([]);
    expect(agentKeysFor({ type: "typing", ticket_id: "t" })).toEqual([]);
  });
  it("lets customers refetch on messages and status changes only", () => {
    expect(customerShouldRefetch({ type: "message.created" })).toBe(true);
    expect(customerShouldRefetch({ type: "ticket.updated", status: "resolved" })).toBe(true);
    expect(customerShouldRefetch({ type: "typing" })).toBe(false);
  });
});

describe("reconnect and URLs", () => {
  it("backs off exponentially with jitter, capped at 30 s", () => {
    expect(reconnectDelay(0, () => 0)).toBe(500);
    expect(reconnectDelay(0, () => 1)).toBe(1000);
    expect(reconnectDelay(3, () => 1)).toBe(8000);
    expect(reconnectDelay(20, () => 1)).toBe(30000);
    expect(reconnectDelay(20, () => 0)).toBe(15000);
  });
  it("builds same-origin socket URLs, or uses the override", () => {
    expect(socketUrl("/ws/agent", { protocol: "http:", host: "localhost:4810" })).toBe("ws://localhost:4810/ws/agent");
    expect(socketUrl("/ws/agent", { protocol: "https:", host: "desk.example" })).toBe("wss://desk.example/ws/agent");
    expect(socketUrl("/ws/agent", { protocol: "http:", host: "x" }, "ws://api:4830/")).toBe("ws://api:4830/ws/agent");
  });
});

describe("typing indicators", () => {
  it("sends at most every 3 seconds", async () => {
    const { shouldSendTyping } = await import("@/lib/live-events");
    expect(shouldSendTyping(0, 3000)).toBe(true);
    expect(shouldSendTyping(10_000, 12_999)).toBe(false);
    expect(shouldSendTyping(10_000, 13_000)).toBe(true);
  });
  it("shows typing for a few seconds after the last event", async () => {
    const { typingActive } = await import("@/lib/live-events");
    expect(typingActive(10_000, 12_000)).toBe(true);
    expect(typingActive(10_000, 15_000)).toBe(false);
    expect(typingActive(null, 1)).toBe(false);
    expect(typingActive(10_000, 9_000)).toBe(false);
  });
  it("keeps the typing fields of an event", () => {
    expect(parseLiveEvent('{"type":"typing","who":"agent","name":"Sam"}')).toEqual({ type: "typing", who: "agent", name: "Sam" });
  });
});

import { qk } from "./query-keys";

/**
 * Live updates over WebSockets carry small invalidations, never data (see the API's
 * core/hub.py): the client refetches what changed over REST. This module is the pure
 * part: parse a frame, decide which query keys it invalidates, and how long to wait
 * before reconnecting.
 */

export interface LiveEvent {
  type: string;
  ticket_id?: string;
  message_id?: string;
  status?: string;
  user_id?: string;
  who?: string;
  name?: string;
}

/** Parse one frame; anything that is not a JSON object with a string type is ignored. */
export function parseLiveEvent(raw: unknown): LiveEvent | null {
  if (typeof raw !== "string" || raw.length > 4000) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const ev = data as Record<string, unknown>;
  if (typeof ev.type !== "string") return null;
  const out: LiveEvent = { type: ev.type };
  for (const key of ["ticket_id", "message_id", "status", "user_id", "who", "name"] as const) {
    if (typeof ev[key] === "string") out[key] = ev[key] as string;
  }
  return out;
}

type Key = readonly unknown[];

/**
 * Agent socket: which React Query keys an event invalidates. Lists and counts refresh
 * on any conversation change; the open conversation only when it is the one named.
 */
export function agentKeysFor(event: LiveEvent): Key[] {
  switch (event.type) {
    case "message.created":
    case "ticket.updated": {
      const keys: Key[] = [qk.ticketLists, qk.counts];
      if (event.ticket_id) keys.push(qk.ticket(event.ticket_id));
      return keys;
    }
    case "presence":
      return [qk.users, qk.me];
    case "ticket.created":
      return [qk.ticketLists, qk.counts];
    default:
      // ready, ping and typing change no server state.
      return [];
  }
}

/** Customer sockets (widget, portal): any message or status change refreshes the thread. */
export function customerShouldRefetch(event: LiveEvent): boolean {
  return event.type === "message.created" || event.type === "ticket.updated";
}

/**
 * Exponential backoff with full jitter, capped: 1 s, 2 s, 4 s ... up to 30 s. `random`
 * is injectable so tests are deterministic.
 */
export function reconnectDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(30_000, 1000 * 2 ** Math.max(0, attempt));
  return Math.round(base / 2 + (random() * base) / 2);
}

/**
 * The WebSocket URL for a path. Agent sockets go through this origin (Next proxies /ws to
 * the API, so the session cookie travels); `NEXT_PUBLIC_WS_URL` points sockets straight
 * at the API when a proxy in front of Next cannot upgrade connections.
 */
export function socketUrl(path: string, location: { protocol: string; host: string }, override?: string | null): string {
  if (override) return `${override.replace(/\/+$/, "")}${path}`;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

/** Typing events go out at most every 3 seconds while someone types. */
export const TYPING_EVERY_MS = 3000;
/** A typing indicator stays up this long after the last event. */
export const TYPING_SHOWN_MS = 5000;

export function shouldSendTyping(lastSentAt: number, now: number, every = TYPING_EVERY_MS): boolean {
  return now - lastSentAt >= every;
}

export function typingActive(lastSeenAt: number | null | undefined, now: number, shown = TYPING_SHOWN_MS): boolean {
  return lastSeenAt != null && now - lastSeenAt >= 0 && now - lastSeenAt < shown;
}

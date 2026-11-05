"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, MessageCircleOffIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { useSocket } from "@/hooks/use-socket";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { customerShouldRefetch, shouldSendTyping, socketUrl, typingActive, type LiveEvent } from "@/lib/live-events";
import { useNow } from "@/hooks/use-now";
import { qk } from "@/lib/query-keys";

import { startSession, useWidgetConversation, useWidgetEmail, useWidgetFeedback, useWidgetHuman, useWidgetRating, useWidgetSend } from "../api";
import {
  aiTyping,
  canAskHuman,
  identityFields,
  initialWidgetState,
  readableOn,
  readIdentity,
  safeColor,
  showEmailForm,
  showRating,
  TOKEN_PREFIX,
  visibleMessages,
  widgetReducer,
  type WidgetIdentity,
} from "../state";

import { WidgetChat } from "./widget-chat";

/** Customers see the API's own explanation; the agent-app wording ("sign in again") does not apply here. */
function widgetError(e: unknown): string {
  if (e instanceof ApiError && e.message && e.status !== 0 && e.status < 500) {
    if (e.status === 401) return `${e.message.replace(/\.?$/, ".")} Reload the page, or contact the site owner if it keeps happening.`;
    return e.message;
  }
  return errorMessage(e);
}

const EMAILED_PREFIX = "supportdesk.widget.emailed.";

/** The API keeps the address as an unverified contact and does not echo it back, so the
 * "we will email you" state is remembered here, per conversation, from the POST's success. */
function emailedFor(ticketId: string): boolean {
  try {
    return localStorage.getItem(EMAILED_PREFIX + ticketId) === "1";
  } catch {
    return false;
  }
}

function rememberEmailed(ticketId: string) {
  try {
    localStorage.setItem(EMAILED_PREFIX + ticketId, "1");
  } catch {
    // Storage blocked: the confirmation lasts this page view.
  }
}

function readToken(key: string): string | null {
  try {
    return localStorage.getItem(TOKEN_PREFIX + key);
  } catch {
    return null;
  }
}

function writeToken(key: string, token: string) {
  try {
    localStorage.setItem(TOKEN_PREFIX + key, token);
  } catch {
    // Storage blocked (private mode, third-party cookies off): the session lasts this page view.
  }
}

/** Tell the page that embeds us something (open, close, unread). Never sends data. */
function toParent(message: Record<string, unknown>) {
  if (typeof window !== "undefined" && window.parent !== window) window.parent.postMessage({ source: "supportdesk", ...message }, "*");
}

/**
 * The widget inside its iframe: starts or resumes the visitor session, renders the
 * conversation, and keeps it live over a WebSocket (polling every 3 s while waiting if
 * the socket is down).
 */
export function WidgetFrame() {
  const params = useSearchParams();
  const key = params.get("key") ?? "";
  const parentOrigin = params.get("origin");
  const [state, dispatch] = React.useReducer(widgetReducer, initialWidgetState);
  const [sendError, setSendError] = React.useState<string | null>(null);
  const client = useQueryClient();
  const started = React.useRef<string | null>(null);

  // The loader sends the signed-in customer (if any) after we say we are ready. Opened on
  // its own (no parent page), or if the loader is silent, the visitor is anonymous.
  const [identity, setIdentity] = React.useState<WidgetIdentity | null | undefined>(undefined);
  React.useEffect(() => {
    function onMessage(e: MessageEvent) {
      if (e.source !== window.parent || (parentOrigin && e.origin !== parentOrigin)) return;
      const d = e.data as { source?: string; type?: string; identity?: unknown } | null;
      if (d?.source !== "supportdesk-loader") return;
      if (d.type === "open") document.querySelector<HTMLTextAreaElement>("textarea")?.focus();
      if (d.type === "identity") setIdentity(readIdentity(d.identity));
    }
    window.addEventListener("message", onMessage);
    if (window.parent === window) {
      setIdentity(null);
    } else {
      toParent({ type: "ready" });
    }
    const t = setTimeout(() => setIdentity((cur) => (cur === undefined ? null : cur)), 1500);
    return () => {
      window.removeEventListener("message", onMessage);
      clearTimeout(t);
    };
  }, [parentOrigin]);

  const identityKey = identity === undefined ? null : JSON.stringify(identity);
  React.useEffect(() => {
    if (identityKey === null || started.current === identityKey) return;
    started.current = identityKey;
    if (!key) {
      dispatch({ type: "failed", error: "This chat is missing its key. Check the script tag on the page." });
      return;
    }
    const who = JSON.parse(identityKey) as WidgetIdentity | null;
    startSession(key, { token: readToken(key), parent_origin: parentOrigin, ...identityFields(who) })
      .then((s) => {
        writeToken(key, s.token);
        dispatch({ type: "session", token: s.token, config: s.config, ticketId: s.ticket_id, customerName: s.customer_name });
        toParent({ type: "config", color: safeColor(s.config.color), position: s.config.position, label: s.config.launcher_label });
      })
      .catch((e: unknown) => dispatch({ type: "failed", error: widgetError(e) }));
  }, [key, parentOrigin, identityKey]);

  React.useEffect(() => {
    if (state.ticketId && !state.emailSent && emailedFor(state.ticketId)) dispatch({ type: "emailSent" });
  }, [state.ticketId, state.emailSent]);

  const [wsUrl, setWsUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    setWsUrl(state.token && state.ticketId ? socketUrl(`/ws/widget/${state.ticketId}?token=${encodeURIComponent(state.token)}`, window.location) : null);
  }, [state.token, state.ticketId]);
  const [agentTypingAt, setAgentTypingAt] = React.useState<{ name: string; at: number } | null>(null);
  const now = useNow(1000);
  const lastTypingSent = React.useRef(0);
  const onEvent = React.useCallback(
    (ev: LiveEvent) => {
      if (ev.type === "typing" && ev.who === "agent") {
        setAgentTypingAt({ name: ev.name || "A teammate", at: Date.now() });
        return;
      }
      if (customerShouldRefetch(ev) && state.ticketId) {
        if (ev.type === "message.created") setAgentTypingAt(null);
        void client.invalidateQueries({ queryKey: qk.widgetConversation(state.ticketId) });
        if (ev.type === "message.created") toParent({ type: "activity" });
      }
    },
    [client, state.ticketId],
  );
  const socket = useSocket(wsUrl, onEvent);
  const conversation = useWidgetConversation(state.token, state.ticketId, socket.status === "open");
  const send = useWidgetSend(state.token);
  const human = useWidgetHuman(state.token);
  const feedback = useWidgetFeedback(state.token);
  const rating = useWidgetRating(state.token);
  const email = useWidgetEmail(state.token);

  if (state.phase === "loading") {
    return (
      <div className="flex h-dvh items-center justify-center bg-background text-muted-foreground" aria-busy>
        <Loader2Icon className="size-5 animate-spin" />
      </div>
    );
  }
  if (state.phase === "error" || !state.config) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-background p-6 text-center">
        <span className="flex size-11 items-center justify-center rounded-xl bg-danger-soft text-danger">
          <MessageCircleOffIcon className="size-5" />
        </span>
        <div className="text-[14px] font-semibold">Chat is unavailable</div>
        <p className="max-w-xs text-[12.5px] leading-relaxed text-muted-foreground">{state.error ?? "Please try again in a moment."}</p>
        <button type="button" onClick={() => window.location.reload()} className="rounded-lg bg-muted px-3 py-1.5 text-[12.5px] font-medium hover:bg-accent">
          Try again
        </button>
        <button type="button" onClick={() => toParent({ type: "close" })} className="text-[12px] text-subtle underline-offset-2 hover:underline">
          Close
        </button>
      </div>
    );
  }

  const cfg = state.config;
  const accent = safeColor(cfg.color);
  const c = conversation.data ?? null;
  const messages = visibleMessages(c);
  const pendingSend = send.isPending ? send.variables?.body : null;

  return (
    <div className="h-dvh">
      <WidgetChat
        title={cfg.title}
        greeting={cfg.greeting}
        company={cfg.company}
        accent={accent}
        accentText={readableOn(accent)}
        suggestions={cfg.suggestions}
        agentsOnline={c?.agents_online ?? cfg.agents_online}
        aiEnabled={cfg.ai_enabled}
        messages={
          pendingSend
            ? [
                ...messages,
                { id: "pending", author_type: "customer", body: pendingSend, citations: [], feedback: null, created_at: new Date().toISOString() },
              ]
            : messages
        }
        typing={send.isPending || aiTyping(c)}
        sending={send.isPending}
        votes={state.votes}
        status={c?.status}
        canAskHuman={canAskHuman(c, state)}
        showEmail={showEmailForm(c, state)}
        emailSent={state.emailSent}
        showRating={showRating(c, state)}
        rated={state.rated}
        ratingPending={rating.isPending}
        emailPending={email.isPending}
        humanPending={human.isPending}
        error={sendError}
        onSend={(body) => {
          setSendError(null);
          send.mutate(
            { body, ticket_id: c && c.status !== "closed" ? state.ticketId : null },
            { onSuccess: (conv) => dispatch({ type: "conversation", ticketId: conv.ticket_id }), onError: (e) => setSendError(`Not sent: ${errorMessage(e)}`) },
          );
        }}
        onVote={(messageId, helpful) => {
          dispatch({ type: "vote", messageId, helpful });
          feedback.mutate({ messageId, helpful }, { onSuccess: () => state.ticketId && void client.invalidateQueries({ queryKey: qk.widgetConversation(state.ticketId) }) });
        }}
        onHuman={() => {
          if (!state.ticketId) return;
          human.mutate(state.ticketId, { onSuccess: () => dispatch({ type: "human" }), onError: (e) => setSendError(errorMessage(e)) });
        }}
        onEmail={(addr, name) =>
          email.mutate(
            { email: addr, name: name || null },
            {
              onSuccess: () => {
                if (state.ticketId) rememberEmailed(state.ticketId);
                dispatch({ type: "emailSent" });
              },
              onError: (e) => setSendError(widgetError(e)),
            },
          )
        }
        onRate={(score, comment) =>
          state.ticketId && rating.mutate({ ticketId: state.ticketId, score, comment }, { onSuccess: () => dispatch({ type: "rated" }), onError: (e) => setSendError(errorMessage(e)) })
        }
        onNewConversation={c && (c.status === "resolved" || c.status === "closed") ? () => dispatch({ type: "newConversation" }) : undefined}
        onClose={() => toParent({ type: "close" })}
        agentTyping={agentTypingAt && typingActive(agentTypingAt.at, now.getTime()) ? agentTypingAt.name : null}
        onTyping={() => {
          const t = Date.now();
          if (!shouldSendTyping(lastTypingSent.current, t)) return;
          lastTypingSent.current = t;
          socket.send({ type: "typing" });
        }}
      />
    </div>
  );
}

"use client";

import { ArrowUpIcon, MailIcon, PlusIcon, UserRoundIcon, XIcon } from "lucide-react";
import * as React from "react";

import type { PublicMessage } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { CustomerThread, RatingForm, TypingBubble } from "./customer-thread";

export interface WidgetChatProps {
  title: string;
  greeting: string;
  company: string;
  accent: string;
  accentText: string;
  suggestions: string[];
  agentsOnline: boolean;
  aiEnabled: boolean;
  messages: PublicMessage[];
  typing: boolean;
  sending: boolean;
  votes: Record<string, boolean>;
  status?: string | null;
  canAskHuman: boolean;
  showEmail: boolean;
  emailSent: boolean;
  showRating: boolean;
  rated: boolean;
  ratingPending?: boolean;
  emailPending?: boolean;
  humanPending?: boolean;
  error?: string | null;
  onSend: (text: string) => void;
  onVote: (messageId: string, helpful: boolean) => void;
  onHuman: () => void;
  onEmail: (email: string, name: string) => void;
  onRate: (score: number, comment: string) => void;
  onNewConversation?: () => void;
  onClose?: () => void;
  /** Name of the agent typing right now, if any. */
  agentTyping?: string | null;
  /** Called on each keystroke; the caller throttles what it sends. */
  onTyping?: () => void;
  /** The designer preview: no focus stealing, no real sends. */
  preview?: boolean;
}

function EmailForm({ onEmail, pending, accent, accentText }: { onEmail: (email: string, name: string) => void; pending: boolean; accent: string; accentText: string }) {
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  return (
    <form
      className="rounded-2xl bg-card p-3.5 shadow-[var(--elev-2)]"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.trim()) onEmail(email.trim(), name.trim());
      }}
    >
      <div className="flex items-center gap-1.5 text-[13px] font-semibold">
        <MailIcon className="size-3.5" /> Nobody is online right now
      </div>
      <p className="mt-0.5 text-[12px] text-muted-foreground">Leave your email and we will reply there. You can close this window.</p>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name (optional)" aria-label="Your name" autoComplete="name" className="mt-2 h-9 w-full rounded-lg bg-muted px-3 text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-label="Your email" autoComplete="email" className="mt-1.5 h-9 w-full rounded-lg bg-muted px-3 text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <button type="submit" disabled={pending || !email.trim()} className="mt-2 h-8 w-full rounded-lg text-[13px] font-semibold disabled:opacity-60" style={{ background: accent, color: accentText }}>
        {pending ? "Saving..." : "Email me the answer"}
      </button>
    </form>
  );
}

/** The chat inside the widget iframe (and its live preview in Settings). Fits 380 x 600. */
export function WidgetChat(p: WidgetChatProps) {
  const [text, setText] = React.useState("");
  const listRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const empty = p.messages.length === 0;

  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [p.messages.length, p.typing, p.showEmail, p.showRating]);

  function send(value: string) {
    const t = value.trim();
    if (!t || p.sending) return;
    p.onSend(t);
    setText("");
    if (!p.preview) inputRef.current?.focus();
  }

  const closed = p.status === "closed";

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <header className="relative shrink-0 px-4 pt-4 pb-5" style={{ background: p.accent, color: p.accentText }}>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[16px] font-semibold tracking-[-0.01em]">{p.title}</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[12px] opacity-85">
              <span className={cn("size-2 rounded-full", p.agentsOnline ? "bg-emerald-300" : "bg-white/50")} aria-hidden />
              {p.aiEnabled ? (p.agentsOnline ? "Instant answers, and the team is online" : "Instant answers, team replies by email") : p.agentsOnline ? "The team is online" : "We reply as soon as we can"}
            </div>
          </div>
          {p.onNewConversation && !empty && (
            <button type="button" onClick={p.onNewConversation} aria-label="Start a new conversation" title="New conversation" className="rounded-lg p-1.5 opacity-80 hover:bg-black/10 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-current">
              <PlusIcon className="size-4" />
            </button>
          )}
          {p.onClose && (
            <button type="button" onClick={p.onClose} aria-label="Close chat" className="rounded-lg p-1.5 opacity-80 hover:bg-black/10 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-current">
              <XIcon className="size-4" />
            </button>
          )}
        </div>
      </header>

      <div ref={listRef} className="-mt-2 min-h-0 flex-1 overflow-y-auto rounded-t-2xl bg-background px-3.5 pt-4 pb-3">
        <ol className="space-y-3" aria-live="polite" aria-label="Conversation">
          <li className="flex items-end gap-2">
            <div className="max-w-[88%] rounded-2xl rounded-bl-md bg-bubble-customer px-3.5 py-2.5 text-[13.5px] leading-relaxed">{p.greeting}</div>
          </li>
          <CustomerThread messages={p.messages} accent={p.accent} accentText={p.accentText} votes={p.votes} onVote={p.preview ? undefined : p.onVote} company={p.company} />
          {p.typing && <TypingBubble />}
          {!p.typing && p.agentTyping && (
            <li className="flex items-center gap-2 pl-9 text-[12px] text-subtle" aria-live="polite">
              <span className="inline-flex gap-0.5" aria-hidden>
                <span className="typing-dot size-1.5 rounded-full bg-subtle" />
                <span className="typing-dot size-1.5 rounded-full bg-subtle" />
                <span className="typing-dot size-1.5 rounded-full bg-subtle" />
              </span>
              {p.agentTyping} is typing...
            </li>
          )}
        </ol>
        {empty && p.suggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap justify-end gap-1.5">
            {p.suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="rounded-full bg-card px-3 py-1.5 text-left text-[12.5px] font-medium shadow-[var(--elev-1)] ring-1 ring-inset transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
                style={{ color: p.accent, ["--tw-ring-color" as string]: `${p.accent}40` }}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="mt-3 space-y-3">
          {p.showEmail && !p.emailSent && <EmailForm onEmail={p.onEmail} pending={!!p.emailPending} accent={p.accent} accentText={p.accentText} />}
          {p.emailSent && <p className="rounded-xl bg-savings-soft px-3 py-2 text-center text-[12.5px] text-savings">Thanks. We will reply by email.</p>}
          {p.showRating && !p.rated && <RatingForm onRate={p.onRate} pending={!!p.ratingPending} accent={p.accent} accentText={p.accentText} />}
          {p.rated && <p className="rounded-xl bg-savings-soft px-3 py-2 text-center text-[12.5px] text-savings">Thank you for rating us.</p>}
        </div>
      </div>

      <div className="shrink-0 bg-background px-3 pt-1 pb-2.5">
        {p.error && <p role="alert" className="mb-1.5 rounded-lg bg-danger-soft px-3 py-1.5 text-[12px] text-danger">{p.error}</p>}
        {p.canAskHuman && !empty && (
          <button type="button" onClick={p.onHuman} disabled={p.humanPending} className="mb-1.5 inline-flex items-center gap-1 rounded-full px-2 py-1 text-[12px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-60">
            <UserRoundIcon className="size-3.5" /> {p.humanPending ? "Connecting..." : "Talk to a person"}
          </button>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
          className="flex items-end gap-2 rounded-2xl bg-card p-1.5 pl-3.5 shadow-[var(--elev-2)] focus-within:ring-2 focus-within:ring-ring"
        >
          <textarea
            ref={inputRef}
            value={text}
            disabled={closed}
            onChange={(e) => {
              setText(e.target.value);
              p.onTyping?.();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
            rows={1}
            maxLength={4000}
            placeholder={closed ? "This conversation is closed. Start a new one." : "Ask a question..."}
            aria-label="Your message"
            className="max-h-28 min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[13.5px] outline-none placeholder:text-faint"
          />
          <button
            type="submit"
            disabled={!text.trim() || p.sending || closed}
            aria-label="Send"
            className="flex size-9 shrink-0 items-center justify-center rounded-xl transition-opacity disabled:opacity-40"
            style={{ background: p.accent, color: p.accentText }}
          >
            <ArrowUpIcon className="size-4" />
          </button>
        </form>
        <p className="mt-1.5 text-center text-[10.5px] text-faint">Answers come from {p.company}&apos;s help docs. Powered by SupportDesk.</p>
      </div>
    </div>
  );
}

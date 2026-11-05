"use client";

import { SparklesIcon, StarIcon, ThumbsDownIcon, ThumbsUpIcon } from "lucide-react";
import * as React from "react";

import { Avatar } from "@/components/avatar";
import { Citations } from "@/components/citations";
import { Markdown } from "@/components/markdown";
import type { PublicMessage } from "@/lib/api/types";
import { cn } from "@/lib/cn";

export function TypingBubble({ label = "Thinking" }: { label?: string }) {
  return (
    <li className="flex items-end gap-2" aria-live="polite">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ai-soft text-ai">
        <SparklesIcon className="size-3.5" />
      </span>
      <div className="rounded-2xl rounded-bl-md bg-bubble-customer px-3.5 py-3">
        <span className="sr-only">{label}</span>
        <span className="inline-flex gap-1" aria-hidden>
          <span className="typing-dot size-1.5 rounded-full bg-subtle" />
          <span className="typing-dot size-1.5 rounded-full bg-subtle" />
          <span className="typing-dot size-1.5 rounded-full bg-subtle" />
        </span>
      </div>
    </li>
  );
}

/**
 * A conversation as the customer sees it: their own messages on the right in the brand
 * colour, the AI and agents on the left with names, handoffs as a centred line, sources
 * under AI answers, and thumbs to say whether an answer helped.
 */
export function CustomerThread({
  messages,
  accent,
  accentText,
  votes,
  onVote,
  company,
  compact = false,
}: {
  messages: PublicMessage[];
  accent: string;
  accentText: string;
  votes: Record<string, boolean>;
  onVote?: (messageId: string, helpful: boolean) => void;
  company: string;
  compact?: boolean;
}) {
  return (
    <>
      {messages.map((m) => {
        if (m.author_type === "system") {
          return (
            <li key={m.id} className="flex justify-center px-3">
              <div className="max-w-[92%] rounded-xl bg-muted px-3 py-2 text-center text-[12px] leading-relaxed text-muted-foreground">{m.body}</div>
            </li>
          );
        }
        if (m.author_type === "customer") {
          return (
            <li key={m.id} className="flex justify-end">
              <div
                className={cn("max-w-[82%] rounded-2xl rounded-br-md px-3.5 py-2.5 leading-relaxed whitespace-pre-wrap break-words", compact ? "text-[13px]" : "text-[13.5px]")}
                style={{ background: accent, color: accentText }}
              >
                {m.body}
              </div>
            </li>
          );
        }
        const ai = m.author_type === "ai";
        const vote = votes[m.id] ?? (m.feedback === "helpful" ? true : m.feedback === "unhelpful" ? false : undefined);
        return (
          <li key={m.id} className="flex items-end gap-2">
            {ai ? (
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ai-soft text-ai" aria-hidden>
                <SparklesIcon className="size-3.5" />
              </span>
            ) : (
              <Avatar name={m.author_name ?? company} size="sm" className="size-7" />
            )}
            <div className="min-w-0 max-w-[85%]">
              <div className="mb-0.5 pl-1 text-[11px] font-medium text-subtle">{ai ? `${company} assistant` : (m.author_name ?? company)}</div>
              <div className={cn("rounded-2xl rounded-bl-md bg-bubble-customer px-3.5 py-2.5", compact ? "text-[13px]" : "text-[13.5px]")}>
                <Markdown source={m.body} compact />
                {ai && m.citations.length > 0 && <Citations citations={m.citations} className="mt-2" />}
              </div>
              {ai && onVote && (
                <div className="mt-1 flex items-center gap-1 pl-1">
                  <span className="text-[11px] text-subtle">{vote === undefined ? "Did this help?" : vote ? "Thanks for the feedback" : "Sorry. A teammate can help."}</span>
                  <button
                    type="button"
                    aria-label="This helped"
                    aria-pressed={vote === true}
                    disabled={vote !== undefined}
                    onClick={() => onVote(m.id, true)}
                    className={cn("rounded-md p-1 text-subtle hover:bg-muted hover:text-foreground disabled:hover:bg-transparent", vote === true && "text-savings")}
                  >
                    <ThumbsUpIcon className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label="This did not help"
                    aria-pressed={vote === false}
                    disabled={vote !== undefined}
                    onClick={() => onVote(m.id, false)}
                    className={cn("rounded-md p-1 text-subtle hover:bg-muted hover:text-foreground disabled:hover:bg-transparent", vote === false && "text-danger")}
                  >
                    <ThumbsDownIcon className="size-3.5" />
                  </button>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </>
  );
}

export function RatingForm({ onRate, pending, accent, accentText }: { onRate: (score: number, comment: string) => void; pending: boolean; accent: string; accentText: string }) {
  const [score, setScore] = React.useState(0);
  const [hover, setHover] = React.useState(0);
  const [comment, setComment] = React.useState("");
  return (
    <form
      className="rounded-2xl bg-card p-3.5 shadow-[var(--elev-2)]"
      onSubmit={(e) => {
        e.preventDefault();
        if (score) onRate(score, comment.trim());
      }}
    >
      <div className="text-[13px] font-semibold">How did we do?</div>
      <div className="mt-2 flex gap-1" role="radiogroup" aria-label="Rating from 1 to 5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={score === n}
            aria-label={`${n} of 5`}
            onMouseEnter={() => setHover(n)}
            onMouseLeave={() => setHover(0)}
            onClick={() => setScore(n)}
            className="rounded-md p-0.5 focus-visible:outline-2 focus-visible:outline-ring"
          >
            <StarIcon className={cn("size-6 transition-colors", (hover || score) >= n ? "fill-warning text-warning" : "text-faint")} />
          </button>
        ))}
      </div>
      {score > 0 && (
        <>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            maxLength={1000}
            placeholder="Anything we could do better? (optional)"
            aria-label="Comment"
            className="mt-2 w-full resize-none rounded-lg bg-muted px-3 py-2 text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button type="submit" disabled={pending} className="mt-2 h-8 w-full rounded-lg text-[13px] font-semibold disabled:opacity-60" style={{ background: accent, color: accentText }}>
            {pending ? "Sending..." : "Send rating"}
          </button>
        </>
      )}
    </form>
  );
}

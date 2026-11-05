"use client";

import { CheckIcon, ChevronDownIcon, LockIcon, PencilIcon, SparklesIcon, ThumbsDownIcon, ThumbsUpIcon, Trash2Icon, UserRoundIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Avatar } from "@/components/avatar";
import { Citations } from "@/components/citations";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Textarea } from "@/components/ui/input";
import { hasDecision, readAiMeta } from "@/lib/ai-meta";
import { errorMessage } from "@/lib/api/errors";
import type { Message, TicketDetail } from "@/lib/api/types";
import { AttachmentList } from "@/components/attachments";
import { cn } from "@/lib/cn";
import { formatDateTime, formatUsd } from "@/lib/format";
import { reasonLabel } from "@/lib/labels";

import { useApprove, useReject } from "../api";

import { DecisionPanel } from "./decision-panel";

export type MessageView = "customer" | "ai" | "agent" | "system" | "note" | "pending" | "draft" | "discarded";

/** Which way to draw a message: decided by author, kind and status. */
export function messageView(m: Pick<Message, "author_type" | "kind" | "status">): MessageView {
  if (m.kind === "note") return "note";
  if (m.status === "rejected" || m.status === "discarded") return "discarded";
  if (m.status === "pending") return "pending";
  if (m.kind === "draft" || m.status === "draft") return "draft";
  if (m.author_type === "system") return "system";
  if (m.author_type === "customer") return "customer";
  if (m.author_type === "ai") return "ai";
  return "agent";
}

function Time({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} className="text-[11px] text-subtle tabular" title={new Date(iso).toLocaleString()}>
      {formatDateTime(iso)}
    </time>
  );
}

function WhyToggle({ open, onToggle, cost }: { open: boolean; onToggle: () => void; cost: number }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium text-ai hover:bg-ai-soft focus-visible:outline-2 focus-visible:outline-ring"
    >
      Why this answer
      <span className="font-normal text-subtle tabular">{formatUsd(cost)}</span>
      <ChevronDownIcon className={cn("size-3 transition-transform", open && "rotate-180")} />
    </button>
  );
}

export function MessageItem({
  message,
  ticketId,
  threshold,
  customerName,
  onEditDraft,
  attachments = [],
}: {
  attachments?: TicketDetail["attachments"];
  message: Message;
  ticketId: string;
  threshold?: number;
  customerName: string;
  onEditDraft: (message: Message) => void;
}) {
  const view = messageView(message);
  const decision = React.useMemo(() => readAiMeta(message.ai_meta), [message.ai_meta]);
  const [why, setWhy] = React.useState(view === "pending");
  const [editing, setEditing] = React.useState(false);
  const [edited, setEdited] = React.useState(message.body);
  const approve = useApprove(ticketId);
  const reject = useReject(ticketId);

  if (view === "system") {
    return (
      <li className="flex flex-col items-center gap-1.5 py-1 text-center">
        <div className="max-w-xl rounded-2xl bg-muted px-3.5 py-1.5 text-[12px] text-muted-foreground">
          <UserRoundIcon className="mr-1 inline size-3.5 -translate-y-px" />
          {message.body}
        </div>
        {decision.reasons.length > 0 && (
          <div className="flex flex-wrap justify-center gap-1 text-[11px] text-subtle">
            Handed over: {decision.reasons.map(reasonLabel).join(", ")}
          </div>
        )}
      </li>
    );
  }

  if (view === "discarded") {
    return (
      <li className="flex justify-end">
        <div className="max-w-[80%] rounded-xl bg-muted/50 px-3 py-2 text-[12px] text-subtle">
          <SparklesIcon className="mr-1 inline size-3" />
          AI answer {message.status === "rejected" ? "rejected" : "discarded"}, not sent: <span className="line-through">{message.body.slice(0, 120)}</span>
          {message.body.length > 120 ? "..." : ""}
        </div>
      </li>
    );
  }

  if (view === "note") {
    return (
      <li className="flex justify-end">
        <div className="w-full max-w-[85%] rounded-2xl bg-note-soft px-4 py-3 sm:max-w-[75%]">
          <div className="mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold text-note">
            <LockIcon className="size-3" /> Internal note by {message.author_name ?? "an agent"}
            <span className="ml-auto font-normal">
              <Time iso={message.created_at} />
            </span>
          </div>
          <Markdown source={message.body} compact className="text-foreground" />
          <AttachmentList items={attachments} className="mt-1.5" />
          <div className="mt-1 text-[11px] text-note/80">Only your team sees this.</div>
        </div>
      </li>
    );
  }

  if (view === "customer") {
    return (
      <li className="flex items-end gap-2">
        <Avatar name={customerName} size="sm" />
        <div className="min-w-0 max-w-[85%] sm:max-w-[72%]">
          <div className="rounded-2xl rounded-bl-md bg-bubble-customer px-4 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap break-words">{message.body}</div>
          <AttachmentList items={attachments} className="mt-1.5" />
          <div className="mt-1 pl-1">
            <Time iso={message.created_at} />
          </div>
        </div>
      </li>
    );
  }

  if (view === "agent") {
    return (
      <li className="flex items-end justify-end gap-2">
        <div className="min-w-0 max-w-[85%] sm:max-w-[72%]">
          <div className="rounded-2xl rounded-br-md bg-bubble-agent px-4 py-2.5 text-[13.5px] leading-relaxed text-bubble-agent-foreground whitespace-pre-wrap break-words">
            {message.body}
          </div>
          <AttachmentList items={attachments} className="mt-1.5 justify-end" />
          <div className="mt-1 flex justify-end gap-1.5 pr-1 text-[11px] text-subtle">
            {message.author_name ?? "Agent"} <span aria-hidden>·</span> <Time iso={message.created_at} />
          </div>
        </div>
        <Avatar name={message.author_name ?? "Agent"} size="sm" />
      </li>
    );
  }

  // AI: sent, held for approval, or a draft for the agent.
  const pendingLike = view === "pending" || view === "draft";
  const busy = approve.isPending || reject.isPending;

  function doApprove(body?: string) {
    approve.mutate(
      { messageId: message.id, body: body ?? null },
      {
        onSuccess: () => {
          toast.success(body && body !== message.body ? "Edited answer sent to the customer." : "Approved and sent to the customer.");
          setEditing(false);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }
  function doDiscard() {
    reject.mutate(message.id, {
      onSuccess: () => toast.success(view === "pending" ? "Answer rejected. The conversation stays with your team." : "Draft discarded."),
      onError: (e) => toast.error(errorMessage(e)),
    });
  }
  // Approving a draft sends it to the customer as written.
  function sendDraft() {
    approve.mutate(
      { messageId: message.id, body: null },
      { onSuccess: () => toast.success("Draft sent to the customer."), onError: (e) => toast.error(errorMessage(e)) },
    );
  }

  return (
    <li className="flex items-end justify-end gap-2">
      <div className={cn("min-w-0", pendingLike ? "w-full max-w-[92%] sm:max-w-[80%]" : "max-w-[85%] sm:max-w-[72%]")}>
        <div
          className={cn(
            "rounded-2xl rounded-br-md px-4 py-3",
            pendingLike ? "bg-card shadow-[var(--elev-2)] outline-2 outline-dashed outline-ai/40" : "bg-ai-soft",
          )}
        >
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11.5px] font-semibold text-ai">
            <SparklesIcon className="size-3" /> AI agent
            {view === "pending" && <Chip tone="warning">Waiting for approval</Chip>}
            {view === "draft" && <Chip tone="info">Draft for you, not sent</Chip>}
            {message.feedback === "helpful" && (
              <Chip tone="success">
                <ThumbsUpIcon /> Helpful
              </Chip>
            )}
            {message.feedback === "unhelpful" && (
              <Chip tone="danger">
                <ThumbsDownIcon /> Not helpful
              </Chip>
            )}
            <span className="ml-auto font-normal">
              <Time iso={message.created_at} />
            </span>
          </div>
          {editing ? (
            <Textarea value={edited} onChange={(e) => setEdited(e.target.value)} rows={6} aria-label="Edit the AI answer" className="text-[13.5px]" autoFocus />
          ) : (
            <Markdown source={message.body} compact className="text-foreground" />
          )}
          <Citations citations={message.citations} className="mt-2.5" />
          {pendingLike && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {view === "pending" ? (
                editing ? (
                  <>
                    <Button size="sm" disabled={busy || !edited.trim()} onClick={() => doApprove(edited.trim())}>
                      <CheckIcon /> Send edited answer
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" disabled={busy} onClick={() => doApprove()}>
                      <CheckIcon /> {approve.isPending ? "Sending..." : "Approve and send"}
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>
                      <PencilIcon /> Edit and send
                    </Button>
                    <Button size="sm" variant="destructive-soft" disabled={busy} onClick={doDiscard}>
                      <Trash2Icon /> Reject
                    </Button>
                  </>
                )
              ) : (
                <>
                  <Button size="sm" disabled={busy} onClick={sendDraft}>
                    <CheckIcon /> {approve.isPending ? "Sending..." : "Send as is"}
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => onEditDraft(message)}>
                    <PencilIcon /> Edit in reply box
                  </Button>
                  <Button size="sm" variant="destructive-soft" disabled={busy} onClick={doDiscard}>
                    <Trash2Icon /> Discard
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
        {hasDecision(decision) && (
          <div className="mt-1 flex flex-col items-end gap-1.5">
            <WhyToggle open={why} onToggle={() => setWhy((w) => !w)} cost={decision.costUsd} />
            {why && (
              <div className="w-full">
                <DecisionPanel decision={decision} threshold={threshold} />
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

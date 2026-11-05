"use client";

import { ArrowLeftIcon, CheckCircle2Icon, PanelRightIcon, RotateCcwIcon, ShieldAlertIcon, SparklesIcon, UserCheckIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { useNow } from "@/hooks/use-now";
import { AttachmentList } from "@/components/attachments";
import { ErrorState } from "@/components/error-state";
import { AiBadge, ApprovalBadge, ChannelIcon, PriorityChip, ReasonChip, SlaChip, StatusChip } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { useSettings } from "@/features/settings/api";
import { errorMessage } from "@/lib/api/errors";
import { channelLabel } from "@/lib/labels";
import { typingActive } from "@/lib/live-events";
import { useTyping } from "@/lib/store";

import { useTicket, useUpdateTicket } from "../api";

import { MessageItem } from "./message-item";
import { ReplyBox, type ReplyBoxHandle } from "./reply-box";
import { SidePanel } from "./side-panel";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || !!target.closest("[role=dialog],[role=listbox],[role=menu]");
}

function CustomerTyping({ ticketId }: { ticketId: string }) {
  const at = useTyping((s) => s.byTicket[ticketId]);
  const now = useNow(1000);
  if (!typingActive(at, now.getTime())) return null;
  return (
    <li className="flex items-center gap-2 pl-8 text-[12px] text-subtle" aria-live="polite">
      <span className="inline-flex gap-0.5">
        <span className="typing-dot size-1.5 rounded-full bg-subtle" />
        <span className="typing-dot size-1.5 rounded-full bg-subtle" />
        <span className="typing-dot size-1.5 rounded-full bg-subtle" />
      </span>
      Customer is typing...
    </li>
  );
}

/**
 * One conversation: the escalation banner (why the AI handed over, and its summary), the
 * transcript with citations and decisions, the reply box, and the customer side panel.
 */
export function Conversation({ id, backHref, onResolvedNext }: { id: string; backHref: string; onResolvedNext: () => void }) {
  const ticket = useTicket(id);
  const update = useUpdateTicket(id);
  const settings = useSettings();
  const { user } = usePermissions();
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const replyRef = React.useRef<ReplyBoxHandle>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const count = ticket.data?.messages.length ?? 0;
  const threshold = settings.data?.policy.min_relevance;

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [count]);

  const t = ticket.data;

  const resolve = React.useCallback(() => {
    if (!t) return;
    update.mutate(
      { status: "resolved" },
      {
        onSuccess: () => {
          toast.success(`#${t.number} resolved.`);
          onResolvedNext();
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }, [t, update, onResolvedNext]);

  // r: reply, e: resolve.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (e.key === "r") {
        e.preventDefault();
        replyRef.current?.focus();
      } else if (e.key === "e" && t && t.status !== "resolved" && t.status !== "closed") {
        e.preventDefault();
        resolve();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [t, resolve]);

  if (ticket.isLoading) {
    return (
      <div className="surface flex h-full flex-col gap-4 p-5" aria-busy aria-label="Loading conversation">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-4 w-1/3" />
        <div className="flex-1 space-y-4 pt-6">
          <Skeleton className="h-14 w-2/3" />
          <Skeleton className="ml-auto h-20 w-3/5" />
          <Skeleton className="h-10 w-1/2" />
        </div>
      </div>
    );
  }
  if (ticket.isError || !t) {
    return (
      <div className="surface flex h-full items-center justify-center">
        <ErrorState error={ticket.error} title="Could not open this conversation" onRetry={() => void ticket.refetch()} />
      </div>
    );
  }

  const escalated = t.escalation_reasons.length > 0 && t.handled_by !== "ai";
  const done = t.status === "resolved" || t.status === "closed";
  const assignedToMe = user && t.assignee_id === user.id;

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="surface flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex flex-wrap items-start gap-3 px-4 pt-3.5 pb-3 sm:px-5">
          <Button variant="subtle" size="icon-sm" className="-ml-1 lg:hidden" nativeButton={false} render={<Link href={backHref} aria-label="Back to the list" />}>
            <ArrowLeftIcon />
          </Button>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-[16px] font-semibold tracking-[-0.015em]">
              <span className="text-subtle tabular">#{t.number}</span> {t.subject || "(no subject)"}
            </h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
              <StatusChip status={t.status} />
              {t.handled_by === "ai" && <AiBadge />}
              {t.ai_resolved && <AiBadge resolved />}
              {t.pending_approval && <ApprovalBadge />}
              <PriorityChip priority={t.priority} quiet />
              <SlaChip state={t.sla_state} dueAt={t.sla_next_due_at} status={t.status} />
              <span className="inline-flex items-center gap-1">
                <ChannelIcon channel={t.channel} /> {channelLabel(t.channel)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {!assignedToMe && !done && user && (
              <Button
                size="sm"
                variant="outline"
                disabled={update.isPending}
                onClick={() => update.mutate({ assignee_id: user.id }, { onSuccess: () => toast.success("Assigned to you."), onError: (e) => toast.error(errorMessage(e)) })}
              >
                <UserCheckIcon /> <span className="hidden sm:inline">Assign to me</span>
              </Button>
            )}
            {done ? (
              <Button
                size="sm"
                variant="outline"
                disabled={update.isPending}
                onClick={() => update.mutate({ status: "open" }, { onSuccess: () => toast.success("Reopened."), onError: (e) => toast.error(errorMessage(e)) })}
              >
                <RotateCcwIcon /> Reopen
              </Button>
            ) : (
              <Button size="sm" disabled={update.isPending} onClick={resolve} title="Resolve (e)">
                <CheckCircle2Icon /> Resolve
              </Button>
            )}
            <Button size="icon-sm" variant="subtle" className="2xl:hidden" aria-label="Customer and details" onClick={() => setDetailsOpen(true)}>
              <PanelRightIcon />
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 sm:px-5">
          {escalated && (
            <div role="note" className="mb-4 rounded-xl bg-warning-soft/70 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2 text-[12.5px] font-semibold text-warning">
                <ShieldAlertIcon className="size-4" /> Handed to your team
                {t.escalation_reasons.map((r) => (
                  <ReasonChip key={r} code={r} />
                ))}
              </div>
              {t.summary ? (
                <p className="mt-2 flex gap-2 text-[13px] leading-relaxed text-foreground">
                  <SparklesIcon className="mt-0.5 size-3.5 shrink-0 text-ai" />
                  <span>
                    <span className="font-medium">AI summary: </span>
                    {t.summary}
                  </span>
                </p>
              ) : (
                <p className="mt-1.5 text-[12.5px] text-muted-foreground">The full transcript is below. The AI did not write a summary for this one.</p>
              )}
            </div>
          )}
          <ol className="space-y-4" aria-label="Transcript">
            {t.messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                ticketId={t.id}
                threshold={threshold}
                customerName={t.customer.name}
                attachments={t.attachments.filter((a) => a.message_id === m.id)}
                onEditDraft={(msg) => replyRef.current?.loadDraft(msg)}
              />
            ))}
            <CustomerTyping ticketId={t.id} />
          </ol>
          {t.attachments.some((a) => !a.message_id || !t.messages.some((m) => m.id === a.message_id)) && (
            <div className="mt-4 rounded-xl bg-muted/60 px-3.5 py-3">
              <div className="mb-2 text-[11.5px] font-semibold text-subtle">Files on this conversation</div>
              <AttachmentList items={t.attachments.filter((a) => !a.message_id || !t.messages.some((m) => m.id === a.message_id))} />
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="px-3 pb-3 sm:px-4">
          <ReplyBox ref={replyRef} ticket={t} />
        </div>
      </div>

      <aside aria-label="Customer and details" className="surface hidden min-h-0 w-[320px] shrink-0 overflow-y-auto p-5 2xl:block">
        <SidePanel ticket={t} />
      </aside>
      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent className="sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Details of #{t.number}</SheetTitle>
          </SheetHeader>
          <SheetBody>
            <SidePanel ticket={t} />
          </SheetBody>
        </SheetContent>
      </Sheet>
    </div>
  );
}

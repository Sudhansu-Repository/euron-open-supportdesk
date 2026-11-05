"use client";

import { ArrowUpRightIcon, CheckCheckIcon, CheckIcon, Loader2Icon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Avatar } from "@/components/avatar";
import { Citations } from "@/components/citations";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/markdown";
import { PageHeader } from "@/components/page-header";
import { ReasonChip, SlaChip } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { readAiMeta } from "@/lib/ai-meta";
import { errorMessage } from "@/lib/api/errors";
import type { Ticket } from "@/lib/api/types";
import { formatRelative, formatUsd } from "@/lib/format";

import { useApproveAny, useTicket, useTickets } from "../api";

function ApprovalCard({ ticket }: { ticket: Ticket }) {
  const detail = useTicket(ticket.id);
  const approve = useApproveAny();
  const pending = detail.data?.messages.filter((m) => m.status === "pending") ?? [];
  const question = [...(detail.data?.messages ?? [])].reverse().find((m) => m.author_type === "customer");

  return (
    <li className="surface overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 px-5 pt-4">
        <Avatar name={ticket.customer.name} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-semibold">
            {ticket.customer.name} <span className="font-normal text-subtle">#{ticket.number}</span>
          </div>
          <div className="truncate text-[12.5px] text-muted-foreground">{ticket.subject}</div>
        </div>
        <SlaChip state={ticket.sla_state} dueAt={ticket.sla_next_due_at} status={ticket.status} />
        <span className="text-[11.5px] text-subtle">{formatRelative(ticket.last_message_at)}</span>
      </div>
      <div className="space-y-3 px-5 py-4">
        {detail.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : detail.isError ? (
          <ErrorState compact error={detail.error} onRetry={() => void detail.refetch()} />
        ) : (
          <>
            {question && (
              <div className="rounded-xl bg-bubble-customer px-3.5 py-2.5 text-[13px] whitespace-pre-wrap">
                <span className="mb-0.5 block text-[11px] font-semibold text-subtle">Customer asked</span>
                {question.body}
              </div>
            )}
            {pending.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">This answer was already handled. The list refreshes in a moment.</p>
            ) : (
              pending.map((m) => {
                const d = readAiMeta(m.ai_meta);
                return (
                  <div key={m.id} className="rounded-xl bg-ai-soft/70 px-3.5 py-3">
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11.5px] font-semibold text-ai">
                      <SparklesIcon className="size-3" /> Proposed AI answer
                      {d.reasons.map((r) => (
                        <ReasonChip key={r} code={r} />
                      ))}
                      <span className="ml-auto font-normal text-subtle">{formatUsd(d.costUsd)}</span>
                    </div>
                    <Markdown source={m.body} compact />
                    <Citations citations={m.citations} className="mt-2" />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        disabled={approve.isPending}
                        onClick={() =>
                          approve.mutate(
                            { messageId: m.id, ticketId: ticket.id },
                            { onSuccess: () => toast.success(`Sent to ${ticket.customer.name}.`), onError: (e) => toast.error(errorMessage(e)) },
                          )
                        }
                      >
                        {approve.isPending ? <Loader2Icon className="animate-spin" /> : <CheckIcon />} Approve and send
                      </Button>
                      <Button size="sm" variant="outline" nativeButton={false} render={<Link href={`/inbox/${ticket.id}?view=approvals`} />}>
                        Edit or reject in the conversation <ArrowUpRightIcon />
                      </Button>
                    </div>
                  </div>
                );
              })
            )}
          </>
        )}
      </div>
    </li>
  );
}

/** Every AI answer waiting for a person, with one-click approval. */
export function ApprovalsScreen() {
  const list = useTickets({ view: "approvals" });
  const tickets = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Approvals"
        description="Sensitive requests (refunds, cancellations, account changes) in approval mode wait here. The AI prepared a grounded answer; a person decides whether it goes out."
      />
      {list.isLoading ? (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <div key={i} className="surface space-y-3 p-5">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-20 w-full" />
            </div>
          ))}
        </div>
      ) : list.isError ? (
        <div className="surface">
          <ErrorState error={list.error} title="Could not load the approval queue" onRetry={() => void list.refetch()} />
        </div>
      ) : tickets.length === 0 ? (
        <div className="surface">
          <EmptyState
            icon={CheckCheckIcon}
            title="Nothing waiting for approval"
            description="When a customer asks for something sensitive and your policy is in approval mode, the AI's answer waits here instead of being sent."
            action={
              <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/settings/policy" />}>
                Review the policy
              </Button>
            }
          />
        </div>
      ) : (
        <ul className="space-y-4">
          {tickets.map((t) => (
            <ApprovalCard key={t.id} ticket={t} />
          ))}
          {list.hasNextPage && (
            <li className="flex justify-center">
              <Button variant="ghost" size="sm" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                Load more
              </Button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

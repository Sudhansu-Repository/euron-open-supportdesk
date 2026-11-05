"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeftIcon, SendIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { StatusChip } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CustomerThread, RatingForm, TypingBubble } from "@/features/widget/components/customer-thread";
import { readableOn, safeColor } from "@/features/widget/state";
import { useHelpCenter } from "@/features/help/api";
import { useSocket } from "@/hooks/use-socket";
import { errorMessage } from "@/lib/api/errors";
import { customerShouldRefetch, socketUrl, type LiveEvent } from "@/lib/live-events";
import { qk } from "@/lib/query-keys";

import { usePortalFeedback, usePortalRating, usePortalReply, usePortalTicket } from "../api";

import { usePortalGuard } from "./portal-tickets";

export function PortalTicket({ slug, id }: { slug: string; id: string }) {
  const { token } = usePortalGuard(slug);
  const help = useHelpCenter(slug);
  const client = useQueryClient();
  const [wsUrl, setWsUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    setWsUrl(token ? socketUrl(`/ws/portal/${id}?token=${encodeURIComponent(token)}`, window.location) : null);
  }, [token, id]);
  const onEvent = React.useCallback((ev: LiveEvent) => customerShouldRefetch(ev) && void client.invalidateQueries({ queryKey: qk.portalTicket(slug, id) }), [client, slug, id]);
  const socket = useSocket(wsUrl, onEvent);
  const ticket = usePortalTicket(slug, token, id, socket.status === "open" ? false : 3000);
  const reply = usePortalReply(slug, token, id);
  const feedback = usePortalFeedback(slug, token);
  const rating = usePortalRating(slug, token, id);
  const [body, setBody] = React.useState("");
  const [votes, setVotes] = React.useState<Record<string, boolean>>({});
  const [rated, setRated] = React.useState(false);
  const accent = safeColor(help.data?.accent_color);

  if (!token || ticket.isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-72" />
      </div>
    );
  }
  if (ticket.isError || !ticket.data) {
    return (
      <div className="surface mx-auto max-w-lg">
        <ErrorState error={ticket.error} title="Could not open this ticket" onRetry={() => void ticket.refetch()} />
      </div>
    );
  }
  const t = ticket.data;
  const messages = t.messages;
  const last = messages.at(-1);
  // The portal view does not say who handles the ticket; a fresh customer message on an open
  // ticket gets a short "thinking" hint while the assistant or a teammate picks it up.
  const thinking = last?.author_type === "customer" && t.status === "open" && Date.now() - new Date(last.created_at).getTime() < 60_000;
  const done = t.status === "resolved" || t.status === "closed";

  return (
    <div className="mx-auto max-w-3xl">
      <Link href={`/help/${slug}/tickets`} className="inline-flex items-center gap-1 text-[13px] font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" /> My tickets
      </Link>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="min-w-0 flex-1 text-[22px] font-semibold tracking-[-0.02em]">
          <span className="text-subtle">#{t.number}</span> {t.subject}
        </h1>
        <StatusChip status={t.status} />
      </div>
      <div className="surface mt-4 p-4 sm:p-6">
        <ol className="space-y-3" aria-live="polite">
          <CustomerThread
            messages={messages}
            accent={accent}
            accentText={readableOn(accent)}
            votes={votes}
            company={help.data?.org_name ?? "Support"}
            onVote={(messageId, helpful) => {
              setVotes((v) => ({ ...v, [messageId]: helpful }));
              feedback.mutate({ messageId, helpful }, { onSuccess: () => void ticket.refetch() });
            }}
          />
          {thinking && <TypingBubble />}
        </ol>
        {done && !rated && t.csat_score == null && (
          <div className="mt-5 max-w-sm">
            <RatingForm
              accent={accent}
              accentText={readableOn(accent)}
              pending={rating.isPending}
              onRate={(score, comment) => rating.mutate({ score, comment }, { onSuccess: () => { setRated(true); toast.success("Thank you for your rating."); }, onError: (e) => toast.error(errorMessage(e)) })}
            />
          </div>
        )}
        {(rated || t.csat_score != null) && <p className="mt-4 text-[12.5px] text-savings">Thanks for rating this conversation.</p>}
      </div>
      <form
        className="mt-4 rounded-2xl bg-card p-3 shadow-[var(--elev-2)]"
        onSubmit={(e) => {
          e.preventDefault();
          if (!body.trim()) return;
          reply.mutate(body.trim(), { onSuccess: () => setBody(""), onError: (err) => toast.error(errorMessage(err)) });
        }}
      >
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
          aria-label="Your reply"
          placeholder={done ? "Write again to reopen this ticket." : "Write a reply..."}
          className="border-0 bg-transparent shadow-none ring-0 focus-visible:ring-0 dark:bg-transparent"
        />
        <div className="mt-2 flex justify-end">
          <Button type="submit" size="sm" disabled={!body.trim() || reply.isPending}>
            <SendIcon /> {reply.isPending ? "Sending..." : "Send"}
          </Button>
        </div>
      </form>
    </div>
  );
}

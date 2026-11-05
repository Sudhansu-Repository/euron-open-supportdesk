"use client";

import { LogOutIcon, PlusIcon, TicketIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { StatusChip } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { formatRelative } from "@/lib/format";

import { usePortalTickets, usePortalToken } from "../api";

/** Sends a signed-out customer to the magic-link page. */
export function usePortalGuard(slug: string) {
  const router = useRouter();
  const t = usePortalToken(slug);
  React.useEffect(() => {
    if (t.ready && !t.token) router.replace(`/help/${slug}/signin`);
  }, [t.ready, t.token, router, slug]);
  return t;
}

export function PortalTickets({ slug }: { slug: string }) {
  const { token, set } = usePortalGuard(slug);
  const tickets = usePortalTickets(slug, token);
  const router = useRouter();
  React.useEffect(() => {
    if (tickets.error instanceof ApiError && tickets.error.status === 401) {
      set(null);
      router.replace(`/help/${slug}/signin`);
    }
  }, [tickets.error, set, router, slug]);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="flex-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">My tickets</h1>
          <p className="mt-0.5 text-[13px] text-muted-foreground">Every conversation you had with us, from the chat, email or here.</p>
        </div>
        <Button nativeButton={false} render={<Link href={`/help/${slug}/tickets/new`} />}>
          <PlusIcon /> New ticket
        </Button>
        <Button variant="ghost" size="icon" aria-label="Sign out" onClick={() => { set(null); router.replace(`/help/${slug}`); }}>
          <LogOutIcon />
        </Button>
      </div>
      <div className="surface p-2">
        {!token || tickets.isLoading ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : tickets.isError ? (
          <ErrorState error={tickets.error} title="Could not load your tickets" onRetry={() => void tickets.refetch()} />
        ) : !tickets.data?.length ? (
          <EmptyState icon={TicketIcon} title="No tickets yet" description="When you ask us something, by chat, email or here, it shows up in this list with its status and our replies." action={<Button size="sm" nativeButton={false} render={<Link href={`/help/${slug}/tickets/new`} />}>Ask a question</Button>} />
        ) : (
          <ul>
            {tickets.data.map((t) => (
              <li key={t.id}>
                <Link href={`/help/${slug}/tickets/${t.id}`} className="flex items-center gap-3 rounded-xl px-3.5 py-3 hover:bg-muted/70 focus-visible:outline-2 focus-visible:outline-ring">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-medium">
                      <span className="text-subtle">#{t.number}</span> {t.subject}
                    </span>
                    {t.preview && <span className="mt-0.5 block truncate text-[12.5px] text-muted-foreground">{t.preview}</span>}
                  </span>
                  <StatusChip status={t.status} />
                  <span className="hidden w-16 text-right text-[12px] text-subtle sm:block">{formatRelative(t.last_message_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

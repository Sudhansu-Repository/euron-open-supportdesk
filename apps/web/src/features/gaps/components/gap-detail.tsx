"use client";

import { ArrowLeftIcon, ArrowUpRightIcon, EyeOffIcon, FileTextIcon, MessageSquareQuoteIcon, RotateCcwIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import { formatRelative } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { useGap, useSetGapStatus } from "../api";

import { gapStatus } from "./gaps-screen";

const REASON: Record<string, string> = {
  no_answer: "Not covered",
  unhelpful: "Marked unhelpful",
  thumbs_down: "Marked unhelpful",
};

export function GapDetailScreen({ id }: { id: string }) {
  const gap = useGap(id);
  const setStatus = useSetGapStatus();
  const { admin } = usePermissions();

  if (gap.isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (gap.isError || !gap.data) {
    return (
      <Surface>
        <ErrorState error={gap.error} title="Could not open this gap" onRetry={() => void gap.refetch()} />
      </Surface>
    );
  }
  const g = gap.data;
  const st = gapStatus(g.status);
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link href="/gaps" className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" /> Knowledge gaps
      </Link>
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{g.title}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12.5px] text-muted-foreground">
            <Chip tone={st.tone}>{st.label}</Chip>
            Asked {g.question_count} time{g.question_count === 1 ? "" : "s"}, last {formatRelative(g.last_seen_at)}
          </div>
        </div>
        {admin && (
          <div className="flex flex-wrap gap-2">
            {g.article_id ? (
              <Button variant="outline" nativeButton={false} render={<Link href={`/knowledge/articles/${g.article_id}`} />}>
                <FileTextIcon /> Open the article
              </Button>
            ) : (
              (g.status === "open" || g.status === "drafted") && (
                <Button nativeButton={false} render={<Link href={`/knowledge/articles/new?gap=${g.id}`} />}>
                  <SparklesIcon /> Draft article
                </Button>
              )
            )}
            {g.status === "open" || g.status === "drafted" ? (
              <Button
                variant="ghost"
                disabled={setStatus.isPending}
                onClick={() => setStatus.mutate({ id: g.id, status: "dismissed" }, { onSuccess: () => toast.success("Gap dismissed."), onError: (e) => toast.error(errorMessage(e)) })}
              >
                <EyeOffIcon /> Dismiss
              </Button>
            ) : (
              g.status === "dismissed" && (
                <Button
                  variant="ghost"
                  disabled={setStatus.isPending}
                  onClick={() => setStatus.mutate({ id: g.id, status: "open" }, { onSuccess: () => toast.success("Gap reopened."), onError: (e) => toast.error(errorMessage(e)) })}
                >
                  <RotateCcwIcon /> Reopen
                </Button>
              )
            )}
          </div>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Surface>
          <SurfaceHeader title="What customers asked" description="Each question the AI could not answer, with the conversation it came from." />
          {g.questions.length === 0 ? (
            <p className="px-5 pb-5 text-[13px] text-muted-foreground">No example questions are stored for this gap.</p>
          ) : (
            <ul className="space-y-2 px-5 pb-5">
              {g.questions.map((q) => (
                <li key={q.id} className="rounded-xl bg-bubble-customer px-3.5 py-2.5">
                  <p className="text-[13px] whitespace-pre-wrap">{q.question}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11.5px] text-subtle">
                    <span>{REASON[q.reason] ?? humanize(q.reason)}</span>
                    <span>{formatRelative(q.created_at)}</span>
                    {q.ticket_id && (
                      <Link href={`/inbox/${q.ticket_id}`} className="ml-auto inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
                        Conversation <ArrowUpRightIcon className="size-3" />
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Surface>
        <Surface>
          <SurfaceHeader title="How your team answered" description="Agent replies that resolved these conversations. The article draft starts from them." />
          {g.replies.length === 0 ? (
            <EmptyState
              compact
              icon={MessageSquareQuoteIcon}
              title="No agent reply yet"
              description="Once someone answers one of these conversations, their reply shows here and seeds the article draft."
            />
          ) : (
            <ul className="space-y-2 px-5 pb-5">
              {g.replies.map((r, i) => (
                <li key={i} className="rounded-xl bg-primary-soft/60 px-3.5 py-2.5 text-[13px] whitespace-pre-wrap">
                  {r}
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>
    </div>
  );
}

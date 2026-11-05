"use client";

import { ArrowLeftIcon, ThumbsDownIcon, ThumbsUpIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { useArticleFeedback, useHelpArticle } from "../api";

export function HelpArticle({ slug, articleSlug }: { slug: string; articleSlug: string }) {
  const article = useHelpArticle(slug, articleSlug);
  const feedback = useArticleFeedback(slug, articleSlug);
  const [voted, setVoted] = React.useState<boolean | null>(null);

  if (article.isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-80" />
      </div>
    );
  }
  if (article.isError || !article.data) {
    return (
      <div className="surface mx-auto max-w-lg">
        <ErrorState error={article.error} title="This article is not available" />
        <div className="flex justify-center pb-6">
          <Button variant="outline" size="sm" nativeButton={false} render={<Link href={`/help/${slug}`} />}>
            Back to the help center
          </Button>
        </div>
      </div>
    );
  }
  const a = article.data;
  return (
    <article className="mx-auto max-w-3xl">
      <Link href={`/help/${slug}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" /> All articles
      </Link>
      <h1 className="mt-4 text-[28px] leading-tight font-semibold tracking-[-0.025em]">{a.title}</h1>
      <p className="mt-1.5 text-[13px] text-muted-foreground">
        {a.category ? `${humanize(a.category)} · ` : ""}Updated {formatDate(a.updated_at)}
      </p>
      <div className="surface mt-6 px-6 py-6 sm:px-8">
        <Markdown source={a.body} />
      </div>
      <div className="mt-6 flex flex-col items-center gap-3 rounded-2xl bg-muted/60 px-5 py-5 text-center sm:flex-row sm:text-left">
        <span className="flex-1 text-[14px] font-medium">{voted === null ? "Was this helpful?" : voted ? "Glad it helped." : "Sorry about that. Ask the assistant in the chat, or open a ticket."}</span>
        {voted === null ? (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={feedback.isPending} onClick={() => feedback.mutate(true, { onSuccess: () => setVoted(true) })}>
              <ThumbsUpIcon /> Yes
            </Button>
            <Button variant="outline" size="sm" disabled={feedback.isPending} onClick={() => feedback.mutate(false, { onSuccess: () => setVoted(false) })}>
              <ThumbsDownIcon /> No
            </Button>
          </div>
        ) : (
          !voted && (
            <Button size="sm" nativeButton={false} render={<Link href={`/help/${slug}/tickets/new`} />}>
              Open a ticket
            </Button>
          )
        )}
      </div>
    </article>
  );
}

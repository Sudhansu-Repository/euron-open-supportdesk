"use client";

import { ArrowRightIcon, FileTextIcon, FolderIcon, MessageCircleIcon, SearchIcon, SearchXIcon, TicketIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { ArticleBrief } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { humanize } from "@/lib/labels";
import { num, obj, str } from "@/lib/read";

import { useHelpArticles, useHelpCenter } from "../api";

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function ArticleList({ slug, items }: { slug: string; items: ArticleBrief[] }) {
  return (
    <ul className="space-y-1">
      {items.map((a) => (
        <li key={a.id}>
          <Link href={`/help/${slug}/articles/${a.slug}`} className="group flex gap-3 rounded-xl px-3.5 py-3 hover:bg-muted/70 focus-visible:outline-2 focus-visible:outline-ring">
            <FileTextIcon className="mt-0.5 size-4 shrink-0 text-primary" />
            <span className="min-w-0 flex-1">
              <span className="block text-[14px] font-medium">{a.title}</span>
              <span className="mt-0.5 line-clamp-2 block text-[12.5px] leading-relaxed text-muted-foreground">{a.excerpt}</span>
            </span>
            <ArrowRightIcon className="mt-1 size-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function HelpHome({ slug }: { slug: string }) {
  const help = useHelpCenter(slug);
  const [q, setQ] = React.useState("");
  const [category, setCategory] = React.useState("");
  const query = useDebounced(q.trim());
  const searching = !!query || !!category;
  const results = useHelpArticles(slug, query, category, searching);
  const categories = (help.data?.categories ?? []).map((c) => ({ name: str(obj(c).name) ?? "general", count: num(obj(c).count) ?? 0 }));

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-3xl px-6 py-10 text-center sm:px-10 sm:py-14" style={{ background: "color-mix(in srgb, var(--primary) 12%, var(--card))" }}>
        {help.data ? (
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.025em] sm:text-[34px]">{help.data.title}</h1>
        ) : (
          <Skeleton className="mx-auto h-9 w-72" />
        )}
        <p className="mt-2 text-[14px] text-muted-foreground">Search the {help.data?.org_name ?? ""} help center, or ask the assistant in the chat.</p>
        <form role="search" onSubmit={(e) => e.preventDefault()} className="relative mx-auto mt-6 max-w-xl">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search articles" aria-label="Search articles" className="h-12 rounded-2xl pl-11 text-[15px] shadow-[var(--elev-2)]" />
        </form>
      </section>

      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Categories">
          <button type="button" onClick={() => setCategory("")} className={cn("rounded-full px-3 py-1.5 text-[13px] font-medium", !category ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground")}>
            All
          </button>
          {categories.map((c) => (
            <button
              key={c.name}
              type="button"
              aria-pressed={category === c.name}
              onClick={() => setCategory(category === c.name ? "" : c.name)}
              className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium", category === c.name ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground")}
            >
              <FolderIcon className="size-3.5" /> {humanize(c.name)} <span className="opacity-70">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section className="surface p-2">
          <h2 className="px-3.5 pt-3 pb-1 text-[15px] font-semibold">{searching ? (query ? `Results for "${query}"` : humanize(category)) : "Popular articles"}</h2>
          {help.isLoading || (searching && results.isLoading) ? (
            <div className="space-y-2 p-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : searching ? (
            results.isError ? (
              <ErrorState compact error={results.error} onRetry={() => void results.refetch()} />
            ) : results.data?.length ? (
              <ArticleList slug={slug} items={results.data} />
            ) : (
              <EmptyState compact icon={SearchXIcon} title="No article matches" description="Try other words, or ask the assistant in the chat: it searches everything we know." action={<Button size="sm" variant="outline" onClick={() => { setQ(""); setCategory(""); }}>Clear the search</Button>} />
            )
          ) : help.data?.popular.length ? (
            <ArticleList slug={slug} items={help.data.popular} />
          ) : (
            <EmptyState compact icon={FileTextIcon} title="No articles published yet" description="This help center is just getting started. The chat assistant and the team can still help you." />
          )}
        </section>
        <aside className="space-y-3">
          <div className="surface p-5">
            <MessageCircleIcon className="size-5 text-primary" />
            <h3 className="mt-2 text-[14px] font-semibold">Ask the assistant</h3>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">Open the chat at the bottom of the page for an instant answer with sources, or a person when you need one.</p>
          </div>
          <div className="surface p-5">
            <TicketIcon className="size-5 text-primary" />
            <h3 className="mt-2 text-[14px] font-semibold">Your tickets</h3>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">Sign in with your email to follow your requests or open a new one.</p>
            <Button size="sm" className="mt-3" nativeButton={false} render={<Link href={`/help/${slug}/tickets`} />}>
              My tickets
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}

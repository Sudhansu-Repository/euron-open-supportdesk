"use client";

import { ChevronRightIcon, LightbulbIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/format";

import { useGaps } from "../api";

export function gapStatus(status: string): { label: string; tone: "warning" | "success" | "neutral" | "info" } {
  if (status === "open") return { label: "Open", tone: "warning" };
  if (status === "drafted") return { label: "Article drafted", tone: "info" };
  if (status === "resolved") return { label: "Closed by an article", tone: "success" };
  return { label: "Dismissed", tone: "neutral" };
}

/** Questions the AI could not answer, clustered: the to-do list for your knowledge. */
export function GapsScreen() {
  const [status, setStatus] = React.useState<"open" | "resolved" | "dismissed">("open");
  const gaps = useGaps(status);
  const rows = [...(gaps.data ?? [])].sort((a, b) => b.question_count - a.question_count);
  const max = Math.max(1, ...rows.map((g) => g.question_count));
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Knowledge gaps"
        description="Questions the AI could not ground in your knowledge, or that customers marked unhelpful, grouped by meaning. Turn the biggest ones into articles and the AI answers them next time."
        actions={
          <Segmented
            ariaLabel="Gap status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "open", label: "Open" },
              { value: "resolved", label: "Closed" },
              { value: "dismissed", label: "Dismissed" },
            ]}
          />
        }
      />
      <Surface>
        {gaps.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : gaps.isError ? (
          <ErrorState error={gaps.error} title="Could not load knowledge gaps" onRetry={() => void gaps.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={LightbulbIcon}
            title={status === "open" ? "No open gaps" : status === "resolved" ? "No gap closed yet" : "Nothing dismissed"}
            description={
              status === "open"
                ? "When the AI cannot find an answer in your knowledge, the question lands here, grouped with similar ones. That is how you learn what to document next."
                : "Gaps closed by a published article, or dismissed as not worth an article, are kept here."
            }
            action={
              <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/knowledge?tab=test" />}>
                Test a question
              </Button>
            }
          />
        ) : (
          <ul className="p-2">
            {rows.map((g) => {
              const st = gapStatus(g.status);
              return (
                <li key={g.id}>
                  <Link href={`/gaps/${g.id}`} className="group flex items-center gap-4 rounded-xl px-3 py-3 hover:bg-muted/70 focus-visible:outline-2 focus-visible:outline-ring">
                    <div className="flex w-14 shrink-0 flex-col items-center">
                      <span className="text-[18px] font-semibold tabular">{g.question_count}</span>
                      <span className="text-[10.5px] text-subtle">asked</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13.5px] font-medium">{g.title}</div>
                      <div className="mt-1.5 h-1 w-full max-w-sm overflow-hidden rounded-full bg-muted" aria-hidden>
                        <div className="h-full rounded-full bg-warning" style={{ width: `${(g.question_count / max) * 100}%` }} />
                      </div>
                    </div>
                    <Chip tone={st.tone} className="hidden sm:inline-flex">
                      {st.label}
                    </Chip>
                    <span className="hidden w-20 text-right text-[12px] text-subtle md:block">{formatRelative(g.last_seen_at)}</span>
                    <ChevronRightIcon className="size-4 text-faint transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Surface>
    </div>
  );
}

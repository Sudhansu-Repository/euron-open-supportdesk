"use client";

import { FileTextIcon, PlusIcon, ThumbsUpIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { formatNumber, formatRatio, formatRelative } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { useArticles } from "../api";

export function ArticlesTab() {
  const articles = useArticles();
  const { admin } = usePermissions();
  const router = useRouter();
  const rows = articles.data ?? [];
  return (
    <Surface>
      <SurfaceHeader
        title="Articles"
        description="Written here in Markdown. Published articles feed the AI and appear in your public help center; drafts do neither."
        action={
          admin && (
            <Button size="sm" nativeButton={false} render={<Link href="/knowledge/articles/new" />}>
              <PlusIcon /> New article
            </Button>
          )
        }
      />
      {articles.isLoading ? (
        <TableSkeleton rows={5} cols={5} />
      ) : articles.isError ? (
        <ErrorState error={articles.error} title="Could not load articles" onRetry={() => void articles.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileTextIcon}
          title="No articles yet"
          description="Articles are the fastest way to fill a gap: write the answer once, publish it, and the AI uses it on the next question."
          action={
            admin ? (
              <Button size="sm" nativeButton={false} render={<Link href="/knowledge/articles/new" />}>
                Write the first article
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Views</TableHead>
              <TableHead className="hidden text-right md:table-cell">Helpful</TableHead>
              <TableHead className="hidden lg:table-cell">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((a) => {
              const votes = a.helpful_yes + a.helpful_no;
              return (
                <TableRow key={a.id} className={admin ? "cursor-pointer" : undefined} onClick={() => admin && router.push(`/knowledge/articles/${a.id}`)}>
                  <TableCell className="max-w-[360px]">
                    {admin ? (
                      <Link href={`/knowledge/articles/${a.id}`} className="block truncate font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                        {a.title}
                      </Link>
                    ) : (
                      <span className="block truncate font-medium">{a.title}</span>
                    )}
                    <span className="text-[12px] text-muted-foreground">{a.category ? humanize(a.category) : "Uncategorised"}</span>
                  </TableCell>
                  <TableCell>
                    <Chip tone={a.status === "published" ? "success" : "neutral"} dot>
                      {a.status === "published" ? "Published" : "Draft"}
                    </Chip>
                  </TableCell>
                  <TableCell className="hidden text-right tabular sm:table-cell">{formatNumber(a.views)}</TableCell>
                  <TableCell className="hidden text-right tabular md:table-cell">
                    {votes ? (
                      <span className="inline-flex items-center gap-1">
                        <ThumbsUpIcon className="size-3 text-subtle" /> {formatRatio(a.helpful_yes / votes, 0)}
                      </span>
                    ) : (
                      <span className="text-subtle">No votes</span>
                    )}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{formatRelative(a.updated_at)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Surface>
  );
}

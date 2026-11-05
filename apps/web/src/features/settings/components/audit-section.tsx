"use client";

import { ScrollTextIcon, SearchIcon } from "lucide-react";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAudit } from "@/features/integrations/api";
import { formatDateTime } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { Card } from "./shared";

export function AuditSection() {
  const [input, setInput] = React.useState("");
  const [action, setAction] = React.useState("");
  const audit = useAudit(action);
  const rows = audit.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Card
      title="Audit log"
      description="Every change to settings, tickets, knowledge, keys and people: who, what and when. Kept for compliance; nobody can edit it."
      action={
        <form onSubmit={(e) => { e.preventDefault(); setAction(input.trim()); }} className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-faint" />
          <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Action, like settings.updated" aria-label="Filter by action" className="h-8 w-60 pl-8 text-[13px]" />
        </form>
      }
    >
      {audit.isLoading ? (
        <TableSkeleton rows={6} cols={4} />
      ) : audit.isError ? (
        <ErrorState compact error={audit.error} onRetry={() => void audit.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState compact icon={ScrollTextIcon} title={action ? "No entry with that action" : "Nothing logged yet"} description={action ? "Check the spelling, or clear the filter to see everything." : "Changes made by your team appear here as they happen."} action={action ? <Button size="sm" variant="outline" onClick={() => { setInput(""); setAction(""); }}>Clear filter</Button> : undefined} />
      ) : (
        <>
          <div className="-mx-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="hidden lg:table-cell">Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground tabular">{formatDateTime(r.at)}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{r.actor_email ?? "System"}</TableCell>
                    <TableCell>
                      <code className="font-mono text-[12px]">{r.action}</code>
                      {r.target_type && <span className="ml-1.5 text-[12px] text-subtle">{humanize(r.target_type)}</span>}
                    </TableCell>
                    <TableCell className="hidden max-w-[320px] truncate font-mono text-[11.5px] text-muted-foreground lg:table-cell">{Object.keys(r.details ?? {}).length ? JSON.stringify(r.details) : ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {audit.hasNextPage && (
            <div className="flex justify-center pt-3">
              <Button size="sm" variant="ghost" onClick={() => void audit.fetchNextPage()} disabled={audit.isFetchingNextPage}>{audit.isFetchingNextPage ? "Loading..." : "Load older"}</Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

"use client";

import { CrownIcon, SearchIcon, UsersIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Avatar } from "@/components/avatar";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber, formatRelative } from "@/lib/format";

import { useCustomers } from "../api";

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Everyone who has written in, with search and a VIP filter. */
export function CustomersScreen() {
  const [q, setQ] = React.useState("");
  const [vip, setVip] = React.useState(false);
  const query = useDebounced(q.trim());
  const list = useCustomers(query, vip);
  const router = useRouter();
  const rows = list.data ?? [];

  return (
    <div>
      <PageHeader title="Customers" description="Everyone who has contacted you, from the widget, email, the portal or the API. Open one to see their history, mark VIPs, or merge duplicates." />
      <Surface>
        <div className="flex flex-wrap items-center gap-3 px-5 pt-4 pb-3">
          <div className="relative w-full max-w-sm">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email" aria-label="Search customers" className="pl-9" />
          </div>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Switch checked={vip} onCheckedChange={setVip} aria-label="Only VIP customers" /> Only VIPs
          </label>
          <span className="ml-auto text-[12px] text-subtle">{list.data ? `${rows.length} shown` : ""}</span>
        </div>
        {list.isLoading ? (
          <TableSkeleton rows={8} cols={5} />
        ) : list.isError ? (
          <ErrorState error={list.error} title="Could not load customers" onRetry={() => void list.refetch()} />
        ) : rows.length === 0 ? (
          query || vip ? (
            <EmptyState icon={SearchIcon} title="No customer matches" description="Try a part of their name or email, or turn off the VIP filter." action={<Button size="sm" variant="outline" onClick={() => { setQ(""); setVip(false); }}>Clear the search</Button>} />
          ) : (
            <EmptyState
              icon={UsersIcon}
              title="No customers yet"
              description="A customer appears here the first time they write: in the website widget, by email, in the portal or through the API."
              action={<Button size="sm" variant="outline" nativeButton={false} render={<Link href="/settings/inboxes" />}>Install the chat widget</Button>}
            />
          )
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">Conversations</TableHead>
                <TableHead className="text-right">Open</TableHead>
                <TableHead className="hidden md:table-cell">Last seen</TableHead>
                <TableHead className="hidden lg:table-cell">Since</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id} className="cursor-pointer" onClick={() => router.push(`/customers/${c.id}`)}>
                  <TableCell>
                    <Link href={`/customers/${c.id}`} className="flex items-center gap-3 outline-none focus-visible:underline" onClick={(e) => e.stopPropagation()}>
                      <Avatar name={c.name} size="sm" />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 font-medium">
                          {c.name}
                          {c.vip && <CrownIcon className="size-3.5 text-warning" aria-label="VIP" />}
                        </span>
                        <span className="block truncate text-[12px] text-muted-foreground">{c.email ?? "No email"}</span>
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular">{formatNumber(c.ticket_count ?? 0)}</TableCell>
                  <TableCell className="text-right tabular">{formatNumber(c.open_count ?? 0)}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{formatRelative(c.last_seen_at)}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{formatRelative(c.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Surface>
    </div>
  );
}

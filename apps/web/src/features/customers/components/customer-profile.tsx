"use client";

import { ArrowLeftIcon, CrownIcon, GitMergeIcon, InboxIcon, MailIcon, PencilIcon, SearchIcon, StarIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Avatar } from "@/components/avatar";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Stat } from "@/components/stat";
import { Surface, SurfaceHeader } from "@/components/surface";
import { AiBadge, ChannelIcon, PriorityChip, StatusChip } from "@/components/ticket-badges";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { Customer, CustomerDetail } from "@/lib/api/types";
import { contactEmail } from "@/lib/contact";
import { formatDate, formatRelative } from "@/lib/format";

import { useCustomer, useCustomers, useMergeCustomers, useUpdateCustomer } from "../api";

function EditDialog({ customer, open, onOpenChange }: { customer: CustomerDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const update = useUpdateCustomer();
  const [name, setName] = React.useState(customer.name);
  const [email, setEmail] = React.useState(customer.email ?? "");
  React.useEffect(() => {
    if (open) {
      setName(customer.name);
      setEmail(customer.email ?? "");
    }
  }, [open, customer]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit customer</DialogTitle>
          <DialogDescription>Fix a name or add the email this person uses, so replies and the portal reach them.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate(
              { id: customer.id, body: { name: name.trim(), email: email.trim() || null } },
              { onSuccess: () => { toast.success("Customer saved."); onOpenChange(false); }, onError: (err) => toast.error(errorMessage(err)) },
            );
          }}
        >
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="c-name"><Input id="c-name" value={name} onChange={(e) => setName(e.target.value)} required /></Field>
            <Field label="Email" htmlFor="c-email" hint="Used for email replies and portal sign-in."><Input id="c-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={update.isPending || !name.trim()}>{update.isPending ? "Saving..." : "Save"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MergeDialog({ customer, open, onOpenChange }: { customer: CustomerDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = React.useState(customer.email?.split("@")[0] ?? customer.name.split(" ")[0] ?? "");
  const results = useCustomers(q.trim(), false);
  const merge = useMergeCustomers();
  const [drop, setDrop] = React.useState<Customer | null>(null);
  const candidates = (results.data ?? []).filter((c) => c.id !== customer.id);
  return (
    <>
      <Dialog open={open && !drop} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Merge a duplicate into {customer.name}</DialogTitle>
            <DialogDescription>The conversations of the duplicate move here and the duplicate is removed. Use it when one person wrote from two addresses or once anonymously.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customers" aria-label="Search for the duplicate" className="pl-9" autoFocus />
            </div>
            {results.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : results.isError ? (
              <ErrorState compact error={results.error} onRetry={() => void results.refetch()} />
            ) : candidates.length === 0 ? (
              <p className="py-4 text-center text-[13px] text-muted-foreground">No other customer matches. Try part of the name or email.</p>
            ) : (
              <ul className="max-h-72 space-y-1 overflow-y-auto">
                {candidates.map((c) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => setDrop(c)} className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
                      <Avatar name={c.name} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">{c.name}</span>
                        <span className="block truncate text-[12px] text-muted-foreground">{c.email ?? "No email"} · {c.ticket_count ?? 0} conversations</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!drop}
        onOpenChange={(o) => !o && setDrop(null)}
        title={`Merge ${drop?.name ?? ""} into ${customer.name}?`}
        description={`${drop?.ticket_count ?? 0} conversation(s) move to ${customer.name}, and ${drop?.name ?? "the duplicate"} is removed. This cannot be undone.`}
        confirmLabel="Merge"
        pending={merge.isPending}
        onConfirm={() =>
          drop &&
          merge.mutate(
            { keep_id: customer.id, drop_id: drop.id },
            {
              onSuccess: () => { toast.success("Customers merged."); setDrop(null); onOpenChange(false); },
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
        }
      />
    </>
  );
}

export function CustomerProfile({ id }: { id: string }) {
  const customer = useCustomer(id);
  const update = useUpdateCustomer();
  const [editOpen, setEditOpen] = React.useState(false);
  const [mergeOpen, setMergeOpen] = React.useState(false);

  if (customer.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-4 sm:grid-cols-3"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (customer.isError || !customer.data) {
    return <Surface><ErrorState error={customer.error} title="Could not load this customer" onRetry={() => void customer.refetch()} /></Surface>;
  }
  const c = customer.data;
  const attributes = Object.entries(c.attributes ?? {});

  return (
    <div className="space-y-5">
      <Link href="/customers" className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" /> All customers
      </Link>
      <div className="flex flex-wrap items-center gap-4">
        <Avatar name={c.name} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="flex items-center gap-2 text-[22px] font-semibold tracking-[-0.02em]">
            {c.name}
            {c.vip && <CrownIcon className="size-5 text-warning" aria-label="VIP" />}
          </h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
            {c.email ? (
              <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1 hover:text-foreground"><MailIcon className="size-3.5" /> {c.email}</a>
            ) : contactEmail(c.attributes) ? (
              <span className="inline-flex items-center gap-1" title="Left in the chat's email form; not verified">
                <MailIcon className="size-3.5" /> Contact email (unverified): {contactEmail(c.attributes)}
              </span>
            ) : (
              <span>No email yet</span>
            )}
            {c.external_id && <span>External id {c.external_id}</span>}
            <span>Customer since {formatDate(c.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex h-9 items-center gap-2 rounded-lg bg-card px-3 text-[13px] shadow-[var(--elev-1)]">
            <Switch
              checked={c.vip}
              disabled={update.isPending}
              onCheckedChange={(vip) => update.mutate({ id: c.id, body: { vip } }, { onSuccess: () => toast.success(vip ? "Marked as VIP. Your policy may route them to a person." : "No longer VIP."), onError: (e) => toast.error(errorMessage(e)) })}
            />
            VIP
          </label>
          <Button variant="outline" onClick={() => setEditOpen(true)}><PencilIcon /> Edit</Button>
          <Button variant="outline" onClick={() => setMergeOpen(true)}><GitMergeIcon /> Merge</Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Conversations" value={c.ticket_count ?? c.tickets.length} icon={InboxIcon} />
        <Stat label="Open now" value={c.open_count ?? 0} />
        <Stat label="Average CSAT" icon={StarIcon} value={c.csat_avg != null ? `${c.csat_avg.toFixed(1)} / 5` : "No ratings"} detail="From ratings after resolution." />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Surface>
          <SurfaceHeader title="Conversation history" description="Newest first. Open one to read it in the inbox." />
          {c.tickets.length === 0 ? (
            <EmptyState compact icon={InboxIcon} title="No conversations" description="This customer has not written yet. Their conversations will appear here." />
          ) : (
            <ul className="px-2 pb-3">
              {c.tickets.map((t) => (
                <li key={t.id}>
                  <Link href={`/inbox/${t.id}`} className="flex flex-wrap items-center gap-2 rounded-xl px-3 py-2.5 hover:bg-muted/70 focus-visible:outline-2 focus-visible:outline-ring">
                    <ChannelIcon channel={t.channel} />
                    <span className="min-w-0 flex-1 truncate text-[13px]"><span className="text-subtle">#{t.number}</span> {t.subject}</span>
                    {t.ai_resolved && <AiBadge resolved />}
                    <PriorityChip priority={t.priority} quiet />
                    <StatusChip status={t.status} />
                    <span className="w-16 text-right text-[11.5px] text-subtle">{formatRelative(t.last_message_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Surface>
        <Surface>
          <SurfaceHeader title="Attributes" description="Sent by your site through identity verification, or set through the API." />
          {attributes.length === 0 ? (
            <p className="px-5 pb-5 text-[12.5px] text-muted-foreground">No attributes. Pass plan, company or any other fields when you identify signed-in customers in the widget.</p>
          ) : (
            <dl className="space-y-2 px-5 pb-5 text-[13px]">
              {attributes.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3"><dt className="text-muted-foreground">{k}</dt><dd className="truncate font-medium">{typeof v === "string" ? v : JSON.stringify(v)}</dd></div>
              ))}
            </dl>
          )}
        </Surface>
      </div>
      <EditDialog customer={c} open={editOpen} onOpenChange={setEditOpen} />
      <MergeDialog customer={c} open={mergeOpen} onOpenChange={setMergeOpen} />
    </div>
  );
}

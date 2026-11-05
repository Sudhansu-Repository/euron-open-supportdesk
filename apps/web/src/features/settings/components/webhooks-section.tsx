"use client";

import { PlusIcon, SendIcon, Trash2Icon, WebhookIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCreateWebhook, useDeleteWebhook, useDeliveries, useTestWebhook, useUpdateWebhook, useWebhookEvents, useWebhooks } from "@/features/integrations/api";
import { errorMessage } from "@/lib/api/errors";
import type { Webhook } from "@/lib/api/types";
import { formatMs, formatRelative } from "@/lib/format";

import { Card, SecretOnce } from "./shared";

function DeliveriesSheet({ hook, onOpenChange }: { hook: Webhook | null; onOpenChange: (o: boolean) => void }) {
  const deliveries = useDeliveries(hook?.id ?? null);
  return (
    <Sheet open={!!hook} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Deliveries</SheetTitle>
          <SheetDescription className="truncate">{hook?.url}</SheetDescription>
        </SheetHeader>
        <SheetBody>
          {deliveries.isLoading ? (
            <TableSkeleton rows={4} cols={4} />
          ) : deliveries.isError ? (
            <ErrorState compact error={deliveries.error} onRetry={() => void deliveries.refetch()} />
          ) : !deliveries.data?.length ? (
            <EmptyState compact icon={SendIcon} title="Nothing delivered yet" description="Send a test ping, or wait for the next event you subscribed to." />
          ) : (
            <ul className="space-y-1.5">
              {deliveries.data.map((d) => (
                <li key={d.id} className="rounded-lg bg-muted/60 px-3 py-2 text-[12.5px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono font-medium">{d.event}</code>
                    <Chip tone={d.status === "delivered" ? "success" : d.status === "failed" || d.status === "dead" ? "danger" : "neutral"}>{d.status}</Chip>
                    {d.response_status != null && <span className="text-muted-foreground">HTTP {d.response_status}</span>}
                    {d.response_ms != null && <span className="text-muted-foreground">{formatMs(d.response_ms)}</span>}
                    <span className="ml-auto text-subtle">{d.attempts} attempt{d.attempts === 1 ? "" : "s"}, {formatRelative(d.created_at)}</span>
                  </div>
                  {d.error && <div className="mt-1 text-danger">{d.error}</div>}
                </li>
              ))}
            </ul>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

export function WebhooksSection() {
  const hooks = useWebhooks();
  const events = useWebhookEvents();
  const create = useCreateWebhook();
  const update = useUpdateWebhook();
  const remove = useDeleteWebhook();
  const test = useTestWebhook();
  const [url, setUrl] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [secret, setSecret] = React.useState<string | null>(null);
  const [log, setLog] = React.useState<Webhook | null>(null);
  const [del, setDel] = React.useState<Webhook | null>(null);
  const all = events.data ?? [];

  React.useEffect(() => {
    if (all.length && picked.length === 0) setPicked(all);
    // Only on first load of the event list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all.length]);

  return (
    <div className="space-y-5">
      <Card title="Add a webhook" description="Signed with HMAC SHA-256 (header X-SupportDesk-Signature), retried with backoff, and disabled after repeated failures. Private and cloud metadata addresses are refused.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ url: url.trim(), events: picked }, { onSuccess: (h) => { setSecret(h.secret); setUrl(""); toast.success("Webhook added."); }, onError: (err) => toast.error(errorMessage(err)) });
          }}
        >
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.example.com/supportdesk" aria-label="Webhook URL" />
            <Button type="submit" disabled={create.isPending || !url.trim() || !picked.length}><PlusIcon /> Add</Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {all.map((ev) => {
              const on = picked.includes(ev);
              return (
                <button key={ev} type="button" aria-pressed={on} onClick={() => setPicked((p) => (on ? p.filter((x) => x !== ev) : [...p, ev]))} className={on ? "rounded-full bg-primary px-2.5 py-1 font-mono text-[11.5px] text-primary-foreground" : "rounded-full bg-muted px-2.5 py-1 font-mono text-[11.5px] text-muted-foreground hover:text-foreground"}>
                  {ev}
                </button>
              );
            })}
          </div>
        </form>
        {secret && <div className="mt-4"><SecretOnce label="Signing secret" value={secret} onDone={() => setSecret(null)} /></div>}
      </Card>
      <Card title="Webhooks">
        {hooks.isLoading ? (
          <TableSkeleton rows={2} cols={4} />
        ) : hooks.isError ? (
          <ErrorState compact error={hooks.error} onRetry={() => void hooks.refetch()} />
        ) : !hooks.data?.length ? (
          <EmptyState compact icon={WebhookIcon} title="No webhooks" description="Push escalations to Slack, new tickets to your CRM, or resolved conversations to your warehouse." />
        ) : (
          <div className="-mx-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead className="hidden md:table-cell">Health</TableHead>
                  <TableHead className="text-right">Active</TableHead>
                  <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {hooks.data.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell className="max-w-[280px]">
                      <div className="truncate font-medium">{h.url}</div>
                      <div className="truncate text-[12px] text-muted-foreground">{h.events.join(", ")}</div>
                      {h.disabled_reason && <div className="mt-0.5 text-[12px] text-danger">Disabled: {h.disabled_reason}</div>}
                    </TableCell>
                    <TableCell className="hidden text-[12.5px] md:table-cell">
                      {h.consecutive_failures > 0 ? <span className="text-warning">{h.consecutive_failures} failures in a row</span> : h.last_success_at ? <span className="text-muted-foreground">OK {formatRelative(h.last_success_at)}</span> : <span className="text-subtle">No delivery yet</span>}
                    </TableCell>
                    <TableCell className="text-right">
                      <Switch
                        checked={h.active}
                        aria-label={h.active ? "Disable webhook" : "Re-enable webhook"}
                        onCheckedChange={(active) => update.mutate({ id: h.id, body: { active } }, { onSuccess: () => toast.success(active ? "Webhook re-enabled." : "Webhook paused."), onError: (e) => toast.error(errorMessage(e)) })}
                      />
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button size="xs" variant="ghost" disabled={test.isPending} onClick={() => test.mutate(h.id, { onSuccess: () => toast.success("Test ping queued. See the deliveries log."), onError: (e) => toast.error(errorMessage(e)) })}>
                        Test
                      </Button>
                      <Button size="xs" variant="ghost" onClick={() => setLog(h)}>Log</Button>
                      <Button size="icon-xs" variant="subtle" aria-label="Delete webhook" onClick={() => setDel(h)}><Trash2Icon /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
      <DeliveriesSheet hook={log} onOpenChange={(o) => !o && setLog(null)} />
      <ConfirmDialog
        open={!!del}
        onOpenChange={(o) => !o && setDel(null)}
        title="Delete this webhook?"
        description="No more events are sent to it. Pending retries are dropped."
        confirmLabel="Delete"
        pending={remove.isPending}
        onConfirm={() => del && remove.mutate(del.id, { onSuccess: () => { toast.success("Webhook deleted."); setDel(null); }, onError: (e) => toast.error(errorMessage(e)) })}
      />
    </div>
  );
}

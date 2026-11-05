"use client";

import { ArrowUpRightIcon, CoinsIcon, CrownIcon, HistoryIcon, MailIcon, PlusIcon, XIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Avatar } from "@/components/avatar";
import { Hint } from "@/components/hint";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { SimpleSelect } from "@/components/ui/select";
import { useCustomer, useUpdateCustomer } from "@/features/customers/api";
import { contactEmail } from "@/lib/contact";
import { useSettings } from "@/features/settings/api";
import { useTeams, useUsers } from "@/features/team/api";
import { errorMessage } from "@/lib/api/errors";
import type { Priority, TicketDetail, TicketPatch, TicketStatus } from "@/lib/api/types";
import { formatDateTime, formatRelative, formatTokens, formatUsd } from "@/lib/format";
import { channelLabel, eventLabel, humanize, intentLabel, PRIORITIES, PRIORITY, sentimentSpec, STATUS } from "@/lib/labels";

import { useUpdateTicket } from "../api";

const NONE = "__none";

function Section({ title, children, icon: Icon, extra }: { title: string; children: React.ReactNode; icon?: React.ComponentType<{ className?: string }>; extra?: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h3 className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.06em] text-subtle uppercase">
        {Icon && <Icon className="size-3.5" />}
        {title}
        {extra}
      </h3>
      {children}
    </section>
  );
}

function Prop({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] items-center gap-2">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function TagEditor({ tags, onChange, disabled }: { tags: string[]; onChange: (tags: string[]) => void; disabled: boolean }) {
  const [value, setValue] = React.useState("");
  function add() {
    const t = value.trim().toLowerCase().replace(/\s+/g, "-");
    if (!t || tags.includes(t)) return setValue("");
    onChange([...tags, t]);
    setValue("");
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((t) => (
        <span key={t} className="inline-flex h-6 items-center gap-1 rounded-full bg-muted pr-1 pl-2 text-[11.5px] font-medium">
          {t}
          <button type="button" aria-label={`Remove tag ${t}`} disabled={disabled} onClick={() => onChange(tags.filter((x) => x !== t))} className="rounded-full p-0.5 text-subtle hover:text-foreground">
            <XIcon className="size-3" />
          </button>
        </span>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
        className="flex items-center"
      >
        <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Add tag" aria-label="Add a tag" className="h-6 w-24 px-2 text-[11.5px]" disabled={disabled} />
        <button type="submit" aria-label="Add tag" disabled={disabled || !value.trim()} className="ml-0.5 rounded p-1 text-subtle hover:text-foreground disabled:opacity-40">
          <PlusIcon className="size-3.5" />
        </button>
      </form>
    </div>
  );
}

export function SidePanel({ ticket }: { ticket: TicketDetail }) {
  const update = useUpdateTicket(ticket.id);
  const users = useUsers();
  const teams = useTeams();
  const settings = useSettings();
  const updateCustomer = useUpdateCustomer();
  const profile = useCustomer(ticket.customer.email ? null : ticket.customer.id);
  const contact = ticket.customer.email ? null : contactEmail(profile.data?.attributes);

  function patch(body: TicketPatch, done: string) {
    update.mutate(body, { onSuccess: () => toast.success(done), onError: (e) => toast.error(errorMessage(e)) });
  }

  const categories = Array.from(new Set([...(settings.data?.categories ?? []), ...(ticket.category ? [ticket.category] : [])]));
  const sentiment = sentimentSpec(ticket.sentiment);
  const customerHref = `/customers/${ticket.customer.id}`;
  const events = [...ticket.events].reverse();

  return (
    <div className="space-y-6">
      <Section title="Customer">
        <div className="flex items-center gap-3">
          <Avatar name={ticket.customer.name} size="lg" />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 truncate text-[14px] font-semibold">
              {ticket.customer.name}
              {ticket.customer.vip && <CrownIcon className="size-3.5 text-warning" aria-label="VIP" />}
            </div>
            {ticket.customer.email ? (
              <a href={`mailto:${ticket.customer.email}`} className="flex items-center gap-1 truncate text-[12.5px] text-muted-foreground hover:text-foreground">
                <MailIcon className="size-3" /> {ticket.customer.email}
              </a>
            ) : contact ? (
              <span className="block truncate text-[12.5px] text-muted-foreground" title="Left in the chat's email form; not verified">
                <span className="text-subtle">Contact email (unverified): </span>
                {contact}
              </span>
            ) : (
              <span className="text-[12.5px] text-subtle">Anonymous visitor, no email yet</span>
            )}
          </div>
        </div>
        <label className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-2 text-[12.5px]">
          <span className="flex items-center gap-1.5">
            VIP customer
            <Hint text="VIP customers are always answered by a person when your policy says so." />
          </span>
          <Switch
            checked={ticket.customer.vip}
            disabled={updateCustomer.isPending}
            onCheckedChange={(vip) =>
              updateCustomer.mutate(
                { id: ticket.customer.id, body: { vip } },
                { onSuccess: () => toast.success(vip ? "Marked as VIP." : "No longer VIP."), onError: (e) => toast.error(errorMessage(e)) },
              )
            }
          />
        </label>
        <Link href={customerHref} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-primary hover:underline">
          Profile and other conversations <ArrowUpRightIcon className="size-3.5" />
        </Link>
      </Section>

      <Section title="Conversation">
        <div className="space-y-2">
          <Prop label="Status">
            <SimpleSelect
              size="sm"
              aria-label="Status"
              value={ticket.status}
              disabled={update.isPending}
              onValueChange={(v) => v !== ticket.status && patch({ status: v as TicketStatus }, `Status set to ${STATUS[v]?.label.toLowerCase() ?? v}.`)}
              options={Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label }))}
            />
          </Prop>
          <Prop label="Priority">
            <SimpleSelect
              size="sm"
              aria-label="Priority"
              value={ticket.priority}
              disabled={update.isPending}
              onValueChange={(v) => v !== ticket.priority && patch({ priority: v as Priority }, `Priority set to ${PRIORITY[v]?.label.toLowerCase() ?? v}.`)}
              options={PRIORITIES.map((p) => ({ value: p, label: PRIORITY[p]?.label ?? p }))}
            />
          </Prop>
          <Prop label="Category">
            <SimpleSelect
              size="sm"
              aria-label="Category"
              value={ticket.category ?? NONE}
              disabled={update.isPending}
              onValueChange={(v) => patch({ category: v === NONE ? "" : v }, "Category updated.")}
              options={[{ value: NONE, label: "None" }, ...categories.map((c) => ({ value: c, label: humanize(c) }))]}
            />
          </Prop>
          <Prop label="Assignee">
            <SimpleSelect
              size="sm"
              aria-label="Assignee"
              value={ticket.assignee_id ?? NONE}
              disabled={update.isPending || users.isLoading}
              onValueChange={(v) => (v === NONE ? patch({ unassign: true }, "Unassigned.") : patch({ assignee_id: v }, `Assigned to ${users.data?.find((u) => u.id === v)?.name ?? "agent"}.`))}
              options={[
                { value: NONE, label: "Unassigned" },
                ...(users.data ?? []).filter((u) => !u.disabled).map((u) => ({ value: u.id, label: `${u.name}${u.availability === "online" ? "" : " (away)"}` })),
              ]}
            />
          </Prop>
          <Prop label="Team">
            <SimpleSelect
              size="sm"
              aria-label="Team"
              value={ticket.team_id ?? NONE}
              disabled={update.isPending}
              onValueChange={(v) => (v === NONE ? patch({ clear_team: true }, "Team cleared.") : patch({ team_id: v }, "Team updated."))}
              options={[{ value: NONE, label: "No team" }, ...(teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))]}
            />
          </Prop>
          <Prop label="Tags">
            <TagEditor tags={ticket.tags} disabled={update.isPending} onChange={(tags) => patch({ tags }, "Tags updated.")} />
          </Prop>
        </div>
        <dl className="grid grid-cols-2 gap-2 pt-1 text-[12px]">
          <div className="rounded-lg bg-muted/60 px-2.5 py-2">
            <dt className="text-subtle">Channel</dt>
            <dd className="font-medium">{channelLabel(ticket.channel)}</dd>
          </div>
          <div className="rounded-lg bg-muted/60 px-2.5 py-2">
            <dt className="text-subtle">Sentiment</dt>
            <dd className="font-medium">{sentiment.label}</dd>
          </div>
          <div className="rounded-lg bg-muted/60 px-2.5 py-2">
            <dt className="text-subtle">Intent</dt>
            <dd className="font-medium">{intentLabel(ticket.intent)}</dd>
          </div>
          <div className="rounded-lg bg-muted/60 px-2.5 py-2">
            <dt className="text-subtle">Language</dt>
            <dd className="font-medium uppercase">{ticket.language ?? "n/a"}</dd>
          </div>
        </dl>
      </Section>

      <Section title="SLA" extra={<Hint term="sla" />}>
        <dl className="space-y-1.5 text-[12.5px]">
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">First response</dt>
            <dd className="text-right font-medium tabular">
              {ticket.first_response_at ? `Done ${formatRelative(ticket.first_response_at)}` : ticket.first_response_due_at ? `Due ${formatDateTime(ticket.first_response_due_at)}` : "No target"}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">Resolution</dt>
            <dd className="text-right font-medium tabular">
              {ticket.resolved_at ? `Done ${formatRelative(ticket.resolved_at)}` : ticket.resolution_due_at ? `Due ${formatDateTime(ticket.resolution_due_at)}` : "No target"}
            </dd>
          </div>
          {ticket.csat_score != null && (
            <div className="flex justify-between gap-2">
              <dt className="flex items-center gap-1 text-muted-foreground">
                CSAT <Hint term="csat" />
              </dt>
              <dd className="text-right font-medium">
                {ticket.csat_score} / 5{ticket.csat_comment ? `: "${ticket.csat_comment}"` : ""}
              </dd>
            </div>
          )}
        </dl>
      </Section>

      <Section title="AI cost of this conversation" icon={CoinsIcon}>
        <div className="flex items-baseline gap-2">
          <span className="text-[22px] font-semibold tracking-[-0.02em] tabular">{formatUsd(ticket.ai_cost_usd)}</span>
          <span className="text-[12px] text-muted-foreground">{formatTokens(ticket.ai_tokens)} tokens</span>
        </div>
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Every model call for this conversation, from the token ledger. Cache hits and extractive answers cost nothing.
        </p>
      </Section>

      <Section title="History" icon={HistoryIcon}>
        {events.length === 0 ? (
          <p className="text-[12.5px] text-muted-foreground">No events yet.</p>
        ) : (
          <ol className="relative space-y-3 pl-4 before:absolute before:top-1 before:bottom-1 before:left-[3px] before:w-px before:bg-hairline">
            {events.slice(0, 30).map((e) => (
              <li key={e.id} className="relative text-[12.5px]">
                <span className="absolute top-1.5 -left-4 size-[7px] rounded-full bg-primary/60" aria-hidden />
                <div className="text-foreground">{eventLabel(e.type, e.data)}</div>
                <div className="text-[11px] text-subtle">
                  {humanize(e.actor_type)}, {formatRelative(e.created_at)}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </div>
  );
}

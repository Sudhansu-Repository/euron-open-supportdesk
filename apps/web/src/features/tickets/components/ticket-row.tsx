"use client";

import Link from "next/link";
import * as React from "react";

import { Avatar } from "@/components/avatar";
import { AiBadge, ApprovalBadge, ChannelIcon, PriorityChip, SlaChip } from "@/components/ticket-badges";
import type { Ticket, User } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

export function TicketRow({
  ticket,
  href,
  selected,
  checked,
  onCheck,
  assignee,
  now,
}: {
  ticket: Ticket;
  href: string;
  selected: boolean;
  checked: boolean;
  onCheck: (checked: boolean) => void;
  assignee?: User;
  now: Date;
}) {
  const unread = ticket.preview_author === "customer" && (ticket.status === "open" || ticket.status === "pending");
  return (
    <li
      data-ticket-id={ticket.id}
      className={cn(
        "group relative flex gap-3 rounded-xl px-3 py-3 transition-colors",
        selected ? "bg-primary-soft" : "hover:bg-muted/70",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheck(e.target.checked)}
        aria-label={`Select conversation ${ticket.number}`}
        className={cn(
          "relative z-10 mt-1 size-3.5 shrink-0 cursor-pointer accent-[var(--primary)] transition-opacity",
          checked ? "opacity-100" : "opacity-40 group-hover:opacity-100 focus-visible:opacity-100",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn("truncate text-[13px]", unread ? "font-semibold text-foreground" : "font-medium text-foreground/90")}>
            {ticket.customer.name}
          </span>
          {ticket.customer.vip && <span className="rounded bg-warning-soft px-1 text-[10px] font-bold text-warning">VIP</span>}
          <span className="ml-auto shrink-0 text-[11.5px] text-subtle tabular" title={new Date(ticket.last_message_at).toLocaleString()}>
            {formatRelative(ticket.last_message_at, now)}
          </span>
        </div>
        <Link
          href={href}
          className="mt-0.5 block truncate text-[13px] text-foreground/85 outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          aria-current={selected ? "true" : undefined}
        >
          <span className="text-subtle tabular">#{ticket.number}</span> {ticket.subject || "(no subject)"}
        </Link>
        {ticket.preview && (
          <p className="mt-0.5 line-clamp-1 text-[12.5px] text-muted-foreground">
            {ticket.preview_author && ticket.preview_author !== "customer" && (
              <span className="text-subtle">{ticket.preview_author === "ai" ? "AI: " : ticket.preview_author === "agent" ? "You: " : ""}</span>
            )}
            {ticket.preview}
          </p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <ChannelIcon channel={ticket.channel} />
          {ticket.handled_by === "ai" && <AiBadge />}
          {ticket.ai_resolved && ticket.status === "resolved" && <AiBadge resolved />}
          {ticket.pending_approval && <ApprovalBadge />}
          <PriorityChip priority={ticket.priority} quiet />
          <SlaChip state={ticket.sla_state} dueAt={ticket.sla_next_due_at} status={ticket.status} />
          {assignee && <Avatar name={assignee.name} size="xs" className="ml-auto" title={`Assigned to ${assignee.name}`} />}
        </div>
      </div>
    </li>
  );
}

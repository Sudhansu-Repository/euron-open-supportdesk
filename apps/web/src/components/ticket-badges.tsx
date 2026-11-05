"use client";

import { AtSignIcon, CodeIcon, GlobeIcon, HourglassIcon, MessageCircleIcon, SparklesIcon, type LucideIcon } from "lucide-react";

import { useNow } from "@/hooks/use-now";
import { Chip } from "@/components/ui/chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { channelLabel, prioritySpec, reasonSpec, statusSpec, STATUS_HINT } from "@/lib/labels";
import { slaBadge } from "@/lib/sla";

const CHANNEL_ICON: Record<string, LucideIcon> = {
  widget: MessageCircleIcon,
  email: AtSignIcon,
  portal: GlobeIcon,
  api: CodeIcon,
};

export function ChannelIcon({ channel, className }: { channel: string; className?: string }) {
  const Icon = CHANNEL_ICON[channel] ?? MessageCircleIcon;
  return (
    <span title={channelLabel(channel)} className="inline-flex">
      <Icon className={cn("size-3.5 text-subtle", className)} aria-label={channelLabel(channel)} />
    </span>
  );
}

function WithTip({ tip, children }: { tip: React.ReactNode; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="inline-flex rounded-full focus-visible:outline-2 focus-visible:outline-ring" />}>
        {children}
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

export function StatusChip({ status }: { status: string }) {
  const s = statusSpec(status);
  return (
    <WithTip tip={STATUS_HINT[status] ?? s.label}>
      <Chip tone={s.tone} dot>
        {s.label}
      </Chip>
    </WithTip>
  );
}

export function PriorityChip({ priority, quiet = false }: { priority: string; quiet?: boolean }) {
  const p = prioritySpec(priority);
  if (quiet && p.rank <= 1) return null;
  return <Chip tone={p.tone}>{p.label}</Chip>;
}

export function SlaChip({ state, dueAt, status }: { state?: string | null; dueAt?: string | null; status: string }) {
  const now = useNow(30_000);
  const b = slaBadge(state, dueAt, status, now);
  if (!b.show) return null;
  return (
    <WithTip tip={b.detail}>
      <Chip tone={b.tone}>
        <HourglassIcon />
        {b.label}
      </Chip>
    </WithTip>
  );
}

export function AiBadge({ resolved = false }: { resolved?: boolean }) {
  return (
    <WithTip tip={resolved ? "Resolved by the AI agent from your knowledge." : "The AI agent is handling this conversation."}>
      <Chip tone="ai">
        <SparklesIcon />
        {resolved ? "AI resolved" : "AI"}
      </Chip>
    </WithTip>
  );
}

export function ApprovalBadge() {
  return (
    <WithTip tip="An AI answer is waiting for a person to approve it before it is sent.">
      <Chip tone="warning">Needs approval</Chip>
    </WithTip>
  );
}

export function ReasonChip({ code }: { code: string }) {
  const r = reasonSpec(code);
  return (
    <WithTip tip={r.explain}>
      <Chip tone={r.tone}>{r.label}</Chip>
    </WithTip>
  );
}

"use client";

import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PriorityChip } from "@/components/ticket-badges";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useSaveSlaPolicies, useSlaPolicies } from "@/features/tickets/api";
import { errorMessage } from "@/lib/api/errors";
import type { Priority, SlaPolicyIn } from "@/lib/api/types";
import { formatMinutes } from "@/lib/format";
import { PRIORITIES } from "@/lib/labels";

import { Card, SaveFooter, sameJson } from "./shared";

const DEFAULTS: Record<Priority, [number, number]> = { urgent: [15, 240], high: [60, 480], normal: [240, 1440], low: [480, 2880] };

export function SlaSection() {
  const policies = useSlaPolicies();
  const save = useSaveSlaPolicies();
  const initial = React.useMemo<SlaPolicyIn[] | null>(() => {
    if (!policies.data) return null;
    return [...PRIORITIES].reverse().map((priority) => {
      const p = policies.data.find((x) => x.priority === priority);
      const [fr, res] = DEFAULTS[priority];
      return { priority, first_response_minutes: p?.first_response_minutes ?? fr, resolution_minutes: p?.resolution_minutes ?? res, enabled: p?.enabled ?? !!p };
    });
  }, [policies.data]);
  const [rows, setRows] = React.useState<SlaPolicyIn[] | null>(initial);
  React.useEffect(() => setRows(initial), [initial]);

  if (policies.isLoading || !rows || !initial) return policies.isError ? <ErrorState error={policies.error} onRetry={() => void policies.refetch()} /> : <Skeleton className="h-80 rounded-2xl" />;
  const set = (i: number, patch: Partial<SlaPolicyIn>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <Card
      title={<>Targets per priority <Hint term="sla" /></>}
      description="Calendar time, in minutes. A conversation turns at risk when less than a quarter of its time is left, and breached when the target passes. Business hours are on the roadmap."
      footer={<SaveFooter dirty={!sameJson(rows, initial)} pending={save.isPending} onReset={() => setRows(initial)} onSave={() => save.mutate(rows, { onSuccess: () => toast.success("SLA policies saved. New due times apply to new conversations."), onError: (e) => toast.error(errorMessage(e)) })} />}
    >
      <div className="space-y-2">
        <div className="hidden grid-cols-[110px_1fr_1fr_70px] gap-3 px-3 text-[11px] font-semibold tracking-[0.04em] text-subtle uppercase sm:grid">
          <span>Priority</span>
          <span>First response</span>
          <span>Resolution</span>
          <span className="text-right">On</span>
        </div>
        {rows.map((r, i) => (
          <div key={r.priority} className="grid grid-cols-2 items-center gap-3 rounded-xl bg-muted/60 px-3 py-2.5 sm:grid-cols-[110px_1fr_1fr_70px]">
            <PriorityChip priority={r.priority} />
            <div className="flex justify-end sm:hidden">
              <Switch checked={r.enabled ?? false} onCheckedChange={(v) => set(i, { enabled: v })} aria-label={`SLA for ${r.priority}`} />
            </div>
            <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <Input type="number" min={1} value={r.first_response_minutes} onChange={(e) => set(i, { first_response_minutes: Number(e.target.value) })} className="h-8 w-24" aria-label={`First response minutes, ${r.priority}`} />
              {formatMinutes(r.first_response_minutes)}
            </label>
            <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <Input type="number" min={1} value={r.resolution_minutes} onChange={(e) => set(i, { resolution_minutes: Number(e.target.value) })} className="h-8 w-24" aria-label={`Resolution minutes, ${r.priority}`} />
              {formatMinutes(r.resolution_minutes)}
            </label>
            <div className="hidden justify-end sm:flex">
              <Switch checked={r.enabled ?? false} onCheckedChange={(v) => set(i, { enabled: v })} aria-label={`SLA for ${r.priority}`} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

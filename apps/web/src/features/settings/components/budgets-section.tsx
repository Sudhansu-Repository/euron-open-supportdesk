"use client";

import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Segmented } from "@/components/segmented";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { Budgets, TokenSaver } from "@/lib/api/types";

import { useSettings, useUpdateSettings } from "../api";

import { Card, SaveFooter, sameJson } from "./shared";

interface Form {
  budgets: Budgets;
  saver: TokenSaver;
}

export function BudgetsSection() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const initial = React.useMemo<Form | null>(() => (settings.data ? { budgets: { ...settings.data.budgets }, saver: { ...settings.data.token_saver } } : null), [settings.data]);
  const [f, setF] = React.useState<Form | null>(initial);
  React.useEffect(() => setF(initial), [initial]);

  if (settings.isLoading || !f || !initial) return settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : <Skeleton className="h-96 rounded-2xl" />;
  const dirty = !sameJson(f, initial);
  const b = (patch: Partial<Budgets>) => setF({ ...f, budgets: { ...f.budgets, ...patch } });
  const s = (patch: Partial<TokenSaver>) => setF({ ...f, saver: { ...f.saver, ...patch } });
  const footer = (
    <SaveFooter
      dirty={dirty}
      pending={update.isPending}
      onReset={() => setF(initial)}
      onSave={() => update.mutate({ budgets: f.budgets, token_saver: f.saver }, { onSuccess: () => toast.success("Budgets and Token Saver saved."), onError: (e) => toast.error(errorMessage(e)) })}
    />
  );

  return (
    <div className="space-y-5">
      <Card title="Hard budgets" description="Reserved atomically before each model call, so they are never exceeded, even under load. 0 means no limit." footer={footer}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tokens per day" htmlFor="b-dt" labelExtra={<Hint term="tokens" />}>
            <Input id="b-dt" type="number" min={0} value={f.budgets.daily_tokens ?? 0} onChange={(e) => b({ daily_tokens: Number(e.target.value) })} />
          </Field>
          <Field label="Tokens per month" htmlFor="b-mt">
            <Input id="b-mt" type="number" min={0} value={f.budgets.monthly_tokens ?? 0} onChange={(e) => b({ monthly_tokens: Number(e.target.value) })} />
          </Field>
          <Field label="Cost per day (USD)" htmlFor="b-dc">
            <Input id="b-dc" type="number" min={0} step="0.01" value={String(f.budgets.daily_cost_usd ?? 0)} onChange={(e) => b({ daily_cost_usd: e.target.value })} />
          </Field>
          <Field label="Cost per month (USD)" htmlFor="b-mc">
            <Input id="b-mc" type="number" min={0} step="0.01" value={String(f.budgets.monthly_cost_usd ?? 0)} onChange={(e) => b({ monthly_cost_usd: e.target.value })} />
          </Field>
        </div>
        <div className="mt-5">
          <div className="mb-1.5 text-[13px] font-medium">When a budget is spent</div>
          <Segmented
            ariaLabel="When a budget is spent"
            className="sm:max-w-md"
            value={f.budgets.on_exhausted ?? "extractive"}
            onChange={(v) => b({ on_exhausted: v })}
            options={[
              { value: "extractive", label: "Answer extractively" },
              { value: "human", label: "Hand to a person" },
            ]}
          />
          <p className="mt-1.5 text-[12px] text-muted-foreground">
            {f.budgets.on_exhausted === "human"
              ? "Every new question goes to your team until the budget resets. Customers never see an error."
              : "The AI keeps answering by quoting your docs, which costs nothing. Customers never see an error."}
          </p>
        </div>
      </Card>

      <Card title="Token Saver" description="Avoid paying twice for the same answer, and keep each call small." footer={footer}>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
            <span>
              <span className="flex items-center gap-1 font-medium">
                Exact answer cache <Hint term="exactCache" />
              </span>
              <span className="block text-[12px] text-muted-foreground">Same question, same knowledge: zero tokens.</span>
            </span>
            <Switch checked={!!f.saver.exact_cache} onCheckedChange={(v) => s({ exact_cache: v })} />
          </label>
          <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
            <span>
              <span className="flex items-center gap-1 font-medium">
                Semantic cache <Hint term="semanticCache" />
              </span>
              <span className="block text-[12px] text-muted-foreground">Same meaning, different words: zero tokens.</span>
            </span>
            <Switch checked={!!f.saver.semantic_cache} onCheckedChange={(v) => s({ semantic_cache: v })} />
          </label>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field label="Semantic match threshold" htmlFor="s-th" hint="How alike two questions must be, 0 to 1. Higher is stricter.">
            <Input id="s-th" type="number" min={0.5} max={1} step={0.01} value={f.saver.semantic_threshold ?? 0.92} onChange={(e) => s({ semantic_threshold: Number(e.target.value) })} />
          </Field>
          <Field label="Cache lifetime (hours)" htmlFor="s-ttl" hint="Also cleared whenever your knowledge changes.">
            <Input id="s-ttl" type="number" min={1} value={f.saver.cache_ttl_hours ?? 168} onChange={(e) => s({ cache_ttl_hours: Number(e.target.value) })} />
          </Field>
          <Field label="History turns sent" htmlFor="s-hist" hint="Older turns are left out to keep calls short.">
            <Input id="s-hist" type="number" min={0} max={20} value={f.saver.history_turns ?? 4} onChange={(e) => s({ history_turns: Number(e.target.value) })} />
          </Field>
        </div>
      </Card>
    </div>
  );
}

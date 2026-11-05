"use client";

import { ShieldCheckIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { Policy } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { humanize, POLICY_MODES, SENSITIVE_INTENTS } from "@/lib/labels";

import { useSettings, useUpdateSettings } from "../api";

import { Card, parseList, SaveFooter, sameJson } from "./shared";

function Toggle({ label, body, checked, onChange }: { label: string; body: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
      <span>
        <span className="font-medium">{label}</span>
        <span className="block text-[12px] text-muted-foreground">{body}</span>
      </span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

function toggle(list: string[], value: string, on: boolean): string[] {
  return on ? Array.from(new Set([...list, value])) : list.filter((x) => x !== value);
}

/** When the AI may answer, decided by code. The model is never asked whether it may. */
export function PolicySection() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const initial = React.useMemo<Policy | null>(() => (settings.data ? { ...settings.data.policy } : null), [settings.data]);
  const [p, setP] = React.useState<Policy | null>(initial);
  const [keywords, setKeywords] = React.useState("");
  React.useEffect(() => {
    setP(initial);
    setKeywords((initial?.custom_sensitive_keywords ?? []).join(", "));
  }, [initial]);

  if (settings.isLoading || !p || !initial) return settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : <Skeleton className="h-96 rounded-2xl" />;
  const next: Policy = { ...p, custom_sensitive_keywords: parseList(keywords) };
  const dirty = !sameJson(next, { ...initial, custom_sensitive_keywords: initial.custom_sensitive_keywords ?? [] });
  const set = (patch: Partial<Policy>) => setP({ ...p, ...patch });
  const categories = Array.from(new Set([...(settings.data?.categories ?? []), ...(p.auto_categories ?? [])]));
  const threshold = p.min_relevance ?? 0.35;

  function save() {
    update.mutate({ policy: next }, { onSuccess: () => toast.success("Policy saved. It applies to the next customer message."), onError: (e) => toast.error(errorMessage(e)) });
  }

  return (
    <div className="space-y-5">
      <div className="flex gap-3 rounded-2xl bg-primary-soft px-5 py-4 text-[13px] leading-relaxed">
        <ShieldCheckIcon className="mt-0.5 size-5 shrink-0 text-primary" />
        <p>
          <span className="font-semibold">Policy is code, not a prompt.</span> Whether an answer is sent, held for approval, kept as a draft or handed to a person is decided by these rules
          after the model answers. A message or a document that says &quot;ignore your rules&quot; cannot change the outcome, because the model is never asked.
        </p>
      </div>

      <Card title="Mode" description="How much the AI may do on its own." footer={<SaveFooter dirty={dirty} pending={update.isPending} onReset={() => { setP(initial); setKeywords((initial.custom_sensitive_keywords ?? []).join(", ")); }} onSave={save} />}>
        <div role="radiogroup" aria-label="AI mode" className="grid gap-2 sm:grid-cols-2">
          {POLICY_MODES.map((m) => {
            const active = (p.mode ?? "approval") === m.value;
            return (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => set({ mode: m.value })}
                className={cn("rounded-xl px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-ring", active ? "bg-primary-soft ring-2 ring-primary/50" : "bg-muted/60 hover:bg-muted")}
              >
                <span className="text-[13.5px] font-semibold">{m.label}</span>
                <span className="mt-0.5 block text-[12.5px] leading-relaxed text-muted-foreground">{m.explain}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-6 space-y-5">
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium">
              Relevance threshold <Hint term="relevanceThreshold" />
              <span className="ml-auto font-semibold tabular">{threshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0.05}
              max={0.95}
              step={0.01}
              value={threshold}
              onChange={(e) => set({ min_relevance: Number(e.target.value) })}
              aria-label="Relevance threshold"
              className="w-full accent-[var(--primary)]"
            />
            <div className="flex justify-between text-[11.5px] text-subtle">
              <span>Answers more, risks more</span>
              <span>Answers less, safer</span>
            </div>
            <p className="mt-1 text-[12px] text-muted-foreground">No passage at or above this score, no answer: the customer gets an honest handoff and a knowledge gap is recorded. Use Test a question to tune it.</p>
          </div>

          <div>
            <div className="mb-2 text-[13px] font-medium">Categories the AI may resolve on its own</div>
            <div className="flex flex-wrap gap-1.5">
              {categories.map((c) => {
                const on = (p.auto_categories ?? []).includes(c);
                return (
                  <button
                    key={c}
                    type="button"
                    aria-pressed={on}
                    onClick={() => set({ auto_categories: toggle(p.auto_categories ?? [], c, !on) })}
                    className={cn("rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring", on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground")}
                  >
                    {humanize(c)}
                  </button>
                );
              })}
            </div>
            <p className="mt-1.5 text-[12px] text-muted-foreground">Other categories get a draft for an agent instead of a sent answer. Edit the category list under Organisation.</p>
          </div>
        </div>
      </Card>

      <Card title="Always involve a person when" description="Each rule escalates with its reason code, shown on the conversation and in analytics.">
        <div className="mb-2 text-[13px] font-medium">Sensitive requests</div>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {SENSITIVE_INTENTS.map((i) => {
            const on = (p.sensitive_intents ?? []).includes(i.value);
            return (
              <label key={i.value} className="flex items-center gap-2.5 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
                <input type="checkbox" checked={on} onChange={(e) => set({ sensitive_intents: toggle(p.sensitive_intents ?? [], i.value, e.target.checked) })} className="size-3.5 accent-[var(--primary)]" />
                {i.label}
              </label>
            );
          })}
        </div>
        <Field className="mt-4" label="Custom sensitive keywords" htmlFor="p-kw" hint="Comma separated. A message containing any of them is treated as sensitive.">
          <Textarea id="p-kw" rows={2} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="chargeback, gdpr, invoice dispute" />
        </Field>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <Toggle label="VIP customers" body="VIPs always get a person, with an AI draft." checked={!!p.escalate_vip} onChange={(v) => set({ escalate_vip: v })} />
          <Toggle label="Frustrated customers" body="Negative sentiment goes to a person." checked={!!p.escalate_negative_sentiment} onChange={(v) => set({ escalate_negative_sentiment: v })} />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Unhelpful answers before handoff" htmlFor="p-unhelp" hint="Thumbs down or 'that did not help'. 0 turns this off.">
            <Input id="p-unhelp" type="number" min={0} max={10} value={p.max_unhelpful ?? 1} onChange={(e) => set({ max_unhelpful: Number(e.target.value) })} />
          </Field>
          <Field label="Max AI turns per conversation" htmlFor="p-turns" hint="After this many AI answers, a person takes over.">
            <Input id="p-turns" type="number" min={1} max={50} value={p.max_ai_turns ?? 6} onChange={(e) => set({ max_ai_turns: Number(e.target.value) })} />
          </Field>
        </div>
      </Card>
    </div>
  );
}

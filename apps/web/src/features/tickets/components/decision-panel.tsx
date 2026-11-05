"use client";

import { BrainIcon, CoinsIcon, GaugeIcon, ScaleIcon, TimerIcon } from "lucide-react";

import { Hint } from "@/components/hint";
import { Chip } from "@/components/ui/chip";
import { answerSource, stepLabel, type AiDecision } from "@/lib/ai-meta";
import { cn } from "@/lib/cn";
import { formatMs, formatTokens, formatUsd } from "@/lib/format";
import { actionSpec, humanize, intentLabel, METHODS, methodLabel, prioritySpec, reasonSpec, sentimentSpec } from "@/lib/labels";

function Row({ label, children, hint }: { label: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <dt className="flex items-center gap-1 text-[12px] text-muted-foreground">
        {label}
        {hint}
      </dt>
      <dd className="text-right text-[12.5px] font-medium text-foreground">{children}</dd>
    </div>
  );
}

/** A 0..1 score as a bar with the threshold marked. */
export function ScoreBar({ value, threshold, label, className }: { value: number; threshold?: number; label: string; className?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const pass = threshold == null || value >= threshold;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={Number(value.toFixed(3))}
      >
        <div className={cn("absolute inset-y-0 left-0 rounded-full", pass ? "bg-primary" : "bg-faint")} style={{ width: `${pct}%` }} />
        {threshold != null && (
          <div className="absolute inset-y-[-2px] w-0.5 rounded bg-foreground/60" style={{ left: `calc(${threshold * 100}% - 1px)` }} aria-hidden />
        )}
      </div>
      <span className={cn("w-10 text-right text-[11.5px] font-semibold tabular", pass ? "text-foreground" : "text-subtle")}>{value.toFixed(2)}</span>
    </div>
  );
}

/**
 * Why the AI did what it did, decided by code (never by the model): the action, the
 * reason codes in words, what triage read, how the answer was produced, and what it cost.
 */
export function DecisionPanel({ decision, threshold }: { decision: AiDecision; threshold?: number }) {
  const action = actionSpec(decision.action);
  const source = answerSource(decision);
  const totalMs = decision.timings.reduce((a, t) => a + (t.step === "total" ? 0 : t.ms), 0);
  return (
    <div className="space-y-3 rounded-xl bg-muted/60 p-3.5 text-left">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold tracking-[0.06em] text-subtle uppercase">Decision by policy</span>
        {decision.action && <Chip tone={action.tone}>{action.label}</Chip>}
        {decision.approvedBy && <Chip tone="success">{decision.editedBy ? "Edited and approved" : "Approved by an agent"}</Chip>}
      </div>
      {action.explain && <p className="text-[12.5px] leading-relaxed text-muted-foreground">{action.explain}</p>}

      {decision.reasons.length > 0 && (
        <ul className="space-y-1.5">
          {decision.reasons.map((r) => {
            const spec = reasonSpec(r);
            return (
              <li key={r} className="flex gap-2 text-[12.5px]">
                <Chip tone={spec.tone} className="mt-px">
                  {spec.label}
                </Chip>
                <span className="text-muted-foreground">{spec.explain}</span>
              </li>
            );
          })}
        </ul>
      )}

      <div className="grid gap-x-6 gap-y-0 sm:grid-cols-2">
        {decision.triage && (
          <dl className="divide-y divide-hairline">
            <div className="flex items-center gap-1.5 pb-1 text-[11.5px] font-semibold text-foreground">
              <BrainIcon className="size-3.5 text-ai" /> Triage
              <Hint term="triage" />
              {decision.triage.source && <span className="font-normal text-subtle">({humanize(decision.triage.source)})</span>}
            </div>
            <Row label="Intent">{intentLabel(decision.triage.intent)}</Row>
            <Row label="Category">{humanize(decision.triage.category) || "General"}</Row>
            <Row label="Sentiment">
              <Chip tone={sentimentSpec(decision.triage.sentiment).tone}>{sentimentSpec(decision.triage.sentiment).label}</Chip>
            </Row>
            <Row label="Priority">{decision.triage.priority ? prioritySpec(decision.triage.priority).label : "Normal"}</Row>
            {decision.triage.sensitive.length > 0 && <Row label="Sensitive">{decision.triage.sensitive.map(intentLabel).join(", ")}</Row>}
          </dl>
        )}
        <dl className="divide-y divide-hairline">
          <div className="flex items-center gap-1.5 pb-1 text-[11.5px] font-semibold text-foreground">
            <ScaleIcon className="size-3.5 text-primary" /> Answer
          </div>
          <Row label="Method" hint={<Hint text={METHODS[source]?.explain ?? "How the answer was produced."} />}>
            {decision.cache ? `${methodLabel(decision.cache)}` : methodLabel(decision.method)}
          </Row>
          <Row label="Grounded" hint={<Hint term="grounding" />}>
            {decision.grounded ? <span className="text-savings">Yes</span> : <span className="text-subtle">No</span>}
          </Row>
          {decision.bestRelevance != null && (
            <div className="py-1.5">
              <div className="mb-1 flex items-center gap-1 text-[12px] text-muted-foreground">
                <GaugeIcon className="size-3" /> Best relevance
                <Hint term="relevanceThreshold" />
              </div>
              <ScoreBar value={decision.bestRelevance} threshold={threshold} label="Best relevance" />
              {threshold != null && <div className="mt-0.5 text-[11px] text-subtle">The mark is your threshold, {threshold.toFixed(2)}.</div>}
            </div>
          )}
          {decision.providerError && <Row label="Provider error">{decision.providerError}</Row>}
        </dl>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-[12px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <CoinsIcon className="size-3.5" />
          <span className="font-semibold text-foreground tabular">{formatTokens(decision.tokens)}</span> tokens
          <Hint term="tokens" />
        </span>
        <span className="inline-flex items-center gap-1.5">
          cost <span className="font-semibold text-foreground tabular">{formatUsd(decision.costUsd)}</span>
        </span>
        {decision.timings.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            <TimerIcon className="size-3.5" />
            {decision.timings
              .filter((t) => t.step !== "total")
              .map((t) => `${stepLabel(t.step)} ${formatMs(t.ms)}`)
              .join(", ")}
            {totalMs > 0 && <span className="text-subtle">(total {formatMs(totalMs)})</span>}
          </span>
        )}
      </div>
    </div>
  );
}

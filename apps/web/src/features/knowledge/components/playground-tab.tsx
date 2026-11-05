"use client";

import { CoinsIcon, FlaskConicalIcon, Loader2Icon, SendIcon, SparklesIcon, TimerIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { citationLabel, safeHref } from "@/components/citations";
import { EmptyState } from "@/components/empty-state";
import { Hint } from "@/components/hint";
import { Markdown } from "@/components/markdown";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { usePermissions } from "@/features/auth/api";
import { ScoreBar } from "@/features/tickets/components/decision-panel";
import { stepLabel } from "@/lib/ai-meta";
import { errorMessage } from "@/lib/api/errors";
import type { Playground } from "@/lib/api/types";
import { formatMs, formatTokens, formatUsd } from "@/lib/format";
import { actionSpec, humanize, intentLabel, methodLabel, reasonSpec, sentimentSpec, WOULD } from "@/lib/labels";
import { obj, str } from "@/lib/read";
import { useUiPrefs } from "@/lib/store";

import { usePlayground } from "../api";

const EXAMPLES = ["How do I reset my password?", "Can I get a refund for last month?", "Do you ship to Canada?"];

function Result({ r }: { r: Playground }) {
  const action = actionSpec(r.action);
  const t = obj(r.triage);
  const sentiment = sentimentSpec(str(t.sentiment));
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <Surface>
        <SurfaceHeader title="What the customer would get" description={`Provider: ${r.provider}. Nothing was sent to anyone.`} />
        <div className="space-y-4 px-5 pb-5">
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={action.tone}>{WOULD[r.action] ?? action.label}</Chip>
            {r.reasons.map((code) => (
              <Chip key={code} tone={reasonSpec(code).tone}>
                {reasonSpec(code).label}
              </Chip>
            ))}
          </div>
          <p className="text-[12.5px] text-muted-foreground">{r.reasons.length ? r.reasons.map((c) => reasonSpec(c).explain).join(" ") : action.explain}</p>
          {r.answer ? (
            <div className="rounded-2xl rounded-bl-md bg-ai-soft px-4 py-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11.5px] font-semibold text-ai">
                <SparklesIcon className="size-3" /> AI answer ({methodLabel(r.method)})
              </div>
              <Markdown source={r.answer} compact />
            </div>
          ) : (
            <div className="rounded-xl bg-muted/60 px-4 py-3 text-[13px] text-muted-foreground">
              No answer: the customer would see an honest handoff to your team, and this question would be recorded as a knowledge gap.
            </div>
          )}
          <dl className="grid grid-cols-2 gap-2 text-[12.5px] sm:grid-cols-4">
            <div className="rounded-lg bg-muted/60 px-3 py-2">
              <dt className="text-subtle">Intent</dt>
              <dd className="font-medium">{intentLabel(str(t.intent))}</dd>
            </div>
            <div className="rounded-lg bg-muted/60 px-3 py-2">
              <dt className="text-subtle">Category</dt>
              <dd className="font-medium">{humanize(str(t.category)) || "General"}</dd>
            </div>
            <div className="rounded-lg bg-muted/60 px-3 py-2">
              <dt className="text-subtle">Sentiment</dt>
              <dd className="font-medium">{sentiment.label}</dd>
            </div>
            <div className="rounded-lg bg-muted/60 px-3 py-2">
              <dt className="flex items-center gap-1 text-subtle">
                Grounded <Hint term="grounding" />
              </dt>
              <dd className="font-medium">{r.grounded ? "Yes" : "No"}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <CoinsIcon className="size-3.5" /> <b className="font-semibold text-foreground tabular">{formatTokens(r.tokens)}</b> tokens, <b className="font-semibold text-foreground tabular">{formatUsd(r.cost_usd)}</b>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <TimerIcon className="size-3.5" />
              {Object.entries(r.timings_ms)
                .map(([k, v]) => `${stepLabel(k)} ${formatMs(v)}`)
                .join(", ") || "n/a"}
            </span>
          </div>
        </div>
      </Surface>
      <Surface>
        <SurfaceHeader
          title={`Retrieved passages (${r.passages.length})`}
          titleExtra={<Hint term="relevanceThreshold" />}
          description={`Only passages at or above the relevance threshold of ${r.threshold.toFixed(2)} may ground an answer. The line on each bar marks it.`}
        />
        {r.passages.length === 0 ? (
          <EmptyState compact icon={FlaskConicalIcon} title="Nothing matched" description="No passage in your knowledge mentions this. Add a source or an article that answers it, then ask again." />
        ) : (
          <ol className="space-y-3 px-5 pb-5">
            {r.passages.map((p, i) => {
              const href = safeHref(p.url);
              const pass = p.relevance >= r.threshold;
              return (
                <li key={p.chunk_id ?? i} className="rounded-xl bg-muted/60 p-3.5">
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="text-[12px] font-semibold text-subtle tabular">#{i + 1}</span>
                    {href ? (
                      <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="truncate text-[13px] font-medium hover:underline">
                        {citationLabel(p)}
                      </a>
                    ) : (
                      <span className="truncate text-[13px] font-medium">{citationLabel(p)}</span>
                    )}
                    <Chip tone={pass ? "success" : "neutral"} className="ml-auto">
                      {pass ? "Above threshold" : "Below threshold"}
                    </Chip>
                  </div>
                  <p className="line-clamp-4 text-[12.5px] leading-relaxed text-muted-foreground">{p.text}</p>
                  <div className="mt-2.5 grid gap-1.5 sm:grid-cols-3">
                    <div>
                      <div className="mb-0.5 flex items-center gap-1 text-[11px] text-subtle">
                        Relevance <Hint term="relevance" />
                      </div>
                      <ScoreBar value={p.relevance} threshold={r.threshold} label="Relevance" />
                    </div>
                    <div>
                      <div className="mb-0.5 flex items-center gap-1 text-[11px] text-subtle">
                        Similarity <Hint term="similarity" />
                      </div>
                      <ScoreBar value={p.similarity} label="Similarity" />
                    </div>
                    <div>
                      <div className="mb-0.5 flex items-center gap-1 text-[11px] text-subtle">
                        Coverage <Hint term="coverage" />
                      </div>
                      <ScoreBar value={p.coverage} label="Coverage" />
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </Surface>
    </div>
  );
}

/** Ask a question as a customer would, and see the whole decision without sending anything. */
export function PlaygroundTab() {
  const [q, setQ] = React.useState("");
  const test = usePlayground();
  const mark = useUiPrefs((s) => s.markTestQuestion);
  const { admin } = usePermissions();

  function ask(question: string) {
    const text = question.trim();
    if (!text) return;
    setQ(text);
    test.mutate(text, { onSuccess: () => mark(), onError: (e) => toast.error(errorMessage(e)) });
  }

  if (!admin) {
    return (
      <Surface>
        <EmptyState icon={FlaskConicalIcon} title="Admins test the knowledge" description="The playground runs the full answer pipeline and may spend tokens, so it is limited to admins. Ask an admin to try your question." />
      </Surface>
    );
  }

  return (
    <div className="space-y-5">
      <Surface className="p-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
          className="flex flex-col gap-2 sm:flex-row"
        >
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask what a customer would ask" aria-label="Test question" className="h-10 flex-1" />
          <Button type="submit" size="lg" disabled={test.isPending || !q.trim()}>
            {test.isPending ? <Loader2Icon className="animate-spin" /> : <SendIcon />}
            {test.isPending ? "Thinking..." : "Test it"}
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] text-subtle">Try:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" onClick={() => ask(ex)} className="rounded-full bg-muted px-2.5 py-1 text-[12px] text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
              {ex}
            </button>
          ))}
        </div>
      </Surface>
      {test.data ? (
        <Result r={test.data} />
      ) : (
        <Surface>
          <EmptyState
            icon={FlaskConicalIcon}
            title="See exactly what the AI would do"
            description="The answer, which passages it found and how relevant they were, the policy decision with its reasons, and the token cost. Nothing is sent to a customer."
          />
        </Surface>
      )}
    </div>
  );
}

"use client";

import {
  BotIcon,
  ClockIcon,
  CoinsIcon,
  DownloadIcon,
  GaugeIcon,
  InboxIcon,
  PiggyBankIcon,
  ShieldCheckIcon,
  ShieldAlertIcon,
  SmileIcon,
  TimerIcon,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { ChartLegend, ChartTooltipCard, CHART } from "@/components/charts/chart-tooltip";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Stat } from "@/components/stat";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Avatar } from "@/components/avatar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { useSettings } from "@/features/settings/api";
import { breakdown, savingsVsSaas, toRows, type Costs, type Overview } from "@/lib/analytics";
import { download } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";
import { formatDate, formatDuration, formatMs, formatNumber, formatRatio, formatTokens, formatUsd, toNumber } from "@/lib/format";
import { channelLabel, humanize, reasonLabel, sentimentSpec } from "@/lib/labels";

import { useChartColors } from "@/hooks/use-chart-colors";

import { useCosts, useOverview, useTeamStats } from "../api";

const RANGES = [7, 30, 90] as const;

function Breakdown({ title, rows, label, color, empty }: { title: string; rows: { key: string; value: number; share: number }[]; label: (k: string) => string; color: string; empty: string }) {
  return (
    <Surface>
      <SurfaceHeader title={title} />
      {rows.length === 0 ? (
        <p className="px-5 pb-5 text-[12.5px] text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-2.5 px-5 pb-5">
          {rows.slice(0, 8).map((r) => (
            <li key={r.key}>
              <div className="mb-1 flex items-center justify-between gap-2 text-[12.5px]">
                <span className="truncate">{label(r.key)}</span>
                <span className="shrink-0 text-muted-foreground tabular">
                  {formatNumber(r.value)} <span className="text-subtle">({formatRatio(r.share, 0)})</span>
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                <div className="h-full rounded-full" style={{ width: `${Math.max(2, r.share * 100)}%`, background: color }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

function VolumeChart({ o }: { o: Overview }) {
  const c = useChartColors();
  const data = o.series.map((p) => ({ ...p, cost_usd: toNumber(p.cost_usd) ?? 0, label: formatDate(p.day).replace(/, \d{4}$/, "") }));
  const empty = data.every((d) => d.created === 0 && d.resolved === 0);
  return (
    <Surface>
      <SurfaceHeader
        title="Conversation volume"
        description="New conversations per day, how many were resolved, and how many of those the AI resolved alone."
        action={
          <ChartLegend
            items={[
              { label: "Created", color: c["chart-1"] },
              { label: "Resolved", color: c["chart-2"] },
              { label: "AI resolved", color: c["chart-3"] },
            ]}
          />
        }
      />
      <div className="h-64 px-2 pb-4">
        {empty ? (
          <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">No conversations in this period yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
              <defs>
                {[
                  ["created", c["chart-1"]],
                  ["resolved", c["chart-2"]],
                  ["ai", c["chart-3"]],
                ].map(([id, c]) => (
                  <linearGradient key={id} id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={c} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke={c["chart-grid"]} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: c["chart-axis"], fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fill: c["chart-axis"], fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
              <Tooltip
                cursor={{ stroke: c["chart-grid"] }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <ChartTooltipCard
                      title={String(label)}
                      rows={[
                        { label: "Created", value: formatNumber(Number(payload[0]?.payload.created)), color: c["chart-1"] },
                        { label: "Resolved", value: formatNumber(Number(payload[0]?.payload.resolved)), color: c["chart-2"] },
                        { label: "AI resolved", value: formatNumber(Number(payload[0]?.payload.ai_resolved)), color: c["chart-3"] },
                        { label: "AI cost", value: formatUsd(Number(payload[0]?.payload.cost_usd)), color: c["chart-4"] },
                      ]}
                    />
                  ) : null
                }
              />
              <Area type="monotone" dataKey="created" stroke={c["chart-1"]} strokeWidth={2} fill="url(#g-created)" />
              <Area type="monotone" dataKey="resolved" stroke={c["chart-2"]} strokeWidth={2} fill="url(#g-resolved)" />
              <Area type="monotone" dataKey="ai_resolved" stroke={c["chart-3"]} strokeWidth={2} fill="url(#g-ai)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Surface>
  );
}

function BudgetMeter({ label, used, limit, format }: { label: string; used: number; limit: number | null; format: (n: number) => string }) {
  const pct = limit && limit > 0 ? Math.min(1, used / limit) : null;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[12.5px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular">
          {format(used)}
          {limit ? <span className="text-subtle"> of {format(limit)}</span> : <span className="text-subtle"> (no limit)</span>}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct != null ? Math.round(pct * 100) : 0}>
        <div className={cn("h-full rounded-full", pct == null ? "bg-faint" : pct >= 0.9 ? "bg-danger" : pct >= 0.7 ? "bg-warning" : "bg-primary")} style={{ width: `${(pct ?? 0) * 100}%` }} />
      </div>
    </div>
  );
}

function CostSection({ o, costs }: { o: Overview; costs: Costs | undefined }) {
  const settings = useSettings();
  const b = settings.data?.budgets;
  const saas = toNumber(o.saas_price_per_resolution_usd) ?? 0.99;
  const perResolution = toNumber(o.cost_per_ai_resolution_usd);
  const cmp = savingsVsSaas(perResolution, saas);
  const saved = (toNumber(o.saas_equivalent_usd) ?? 0) - (toNumber(o.totals.cost_usd) ?? 0);
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <Surface className="overflow-hidden">
        <div className="bg-gradient-to-br from-ai-soft to-transparent px-5 pt-5 pb-4">
          <div className="flex items-center gap-2 text-[12px] font-semibold tracking-[0.06em] text-ai uppercase">
            <PiggyBankIcon className="size-4" /> Cost per AI resolution
            <Hint term="aiResolution" />
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              <div className="text-[34px] leading-none font-semibold tracking-[-0.03em] tabular">{perResolution != null ? formatUsd(perResolution) : "n/a"}</div>
              <div className="mt-1 text-[12px] text-muted-foreground">yours, from the token ledger</div>
            </div>
            <div>
              <div className="text-[22px] leading-none font-semibold text-muted-foreground tabular">{formatUsd(saas)}</div>
              <div className="mt-1 text-[12px] text-muted-foreground">typical SaaS price per resolution</div>
            </div>
          </div>
          <p className="mt-4 max-w-xl text-[13px] leading-relaxed text-foreground">
            SaaS AI agents bill about {formatUsd(saas)} per resolution.{" "}
            {o.totals.ai_resolved === 0
              ? "Once the AI resolves conversations, you will see your own cost per resolution here."
              : cmp.cheaper
                ? `Your ${formatNumber(o.totals.ai_resolved)} AI resolutions would have cost about ${formatUsd(o.saas_equivalent_usd)} there; the tokens cost you ${formatUsd(o.totals.cost_usd)}${cmp.ratio ? `, about ${Math.round(cmp.ratio).toLocaleString("en-US")} times less` : ""}.`
                : `Your ${formatNumber(o.totals.ai_resolved)} AI resolutions cost ${formatUsd(o.totals.cost_usd)} in tokens, against about ${formatUsd(o.saas_equivalent_usd)} at the SaaS price.`}{" "}
            <span className="text-muted-foreground">Server and seat costs are not included on either side.</span>
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-px bg-hairline sm:grid-cols-4">
          {[
            { k: "Model spend", v: formatUsd(o.totals.cost_usd) },
            { k: "SaaS equivalent", v: formatUsd(o.saas_equivalent_usd) },
            { k: "Tokens", v: formatTokens(o.totals.tokens) },
            { k: "Cache hits", v: `${formatNumber(o.totals.cache_hits)} (${formatUsd(o.totals.saved_cost_usd)} saved)` },
          ].map((x) => (
            <div key={x.k} className="bg-card px-4 py-3">
              <dt className="text-[11.5px] text-subtle">{x.k}</dt>
              <dd className="mt-0.5 text-[14px] font-semibold tabular">{x.v}</dd>
            </div>
          ))}
        </dl>
        {saved > 0 && <p className="px-5 py-3 text-[12px] text-savings">Difference over this period: {formatUsd(saved)}.</p>}
      </Surface>

      <Surface>
        <SurfaceHeader title="Budget usage" description="Hard limits reserved before every model call. When spent, the AI falls back as set in Budgets." titleExtra={<GaugeIcon className="size-4 text-subtle" />} />
        <div className="space-y-4 px-5 pb-5">
          {!costs ? (
            <Skeleton className="h-24" />
          ) : (
            <>
              <BudgetMeter label="Tokens today" used={costs.usage.today?.tokens ?? 0} limit={b?.daily_tokens ?? null} format={formatTokens} />
              <BudgetMeter label="Cost today" used={toNumber(costs.usage.today?.cost_usd) ?? 0} limit={toNumber(b?.daily_cost_usd)} format={formatUsd} />
              <BudgetMeter label="Tokens this month" used={costs.usage.month?.tokens ?? 0} limit={b?.monthly_tokens ?? null} format={formatTokens} />
              <BudgetMeter label="Cost this month" used={toNumber(costs.usage.month?.cost_usd) ?? 0} limit={toNumber(b?.monthly_cost_usd)} format={formatUsd} />
              {(costs.usage.today?.blocked ?? 0) + (costs.usage.month?.blocked ?? 0) > 0 && (
                <p className="text-[12px] text-warning">{formatNumber((costs.usage.month?.blocked ?? 0) || (costs.usage.today?.blocked ?? 0))} calls were stopped by the budget before they were made.</p>
              )}
            </>
          )}
        </div>
      </Surface>
    </div>
  );
}

function LedgerTable({ costs, loading, error, retry }: { costs?: Costs; loading: boolean; error: unknown; retry: () => void }) {
  return (
    <Surface>
      <SurfaceHeader title="Token ledger" description="Every model call by purpose and model: tokens, cost, cache hits and latency." titleExtra={<Hint term="tokens" />} />
      {loading ? (
        <TableSkeleton rows={4} cols={6} />
      ) : error ? (
        <ErrorState compact error={error} onRetry={retry} />
      ) : !costs?.rows.length ? (
        <EmptyState compact icon={CoinsIcon} title="No model calls yet" description="With the extractive provider the AI answers without a model, so nothing is billed. Calls to Ollama, OpenAI-compatible or Anthropic models land here." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Purpose</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="hidden text-right md:table-cell">Tokens in / out</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="hidden text-right lg:table-cell">Cache hits</TableHead>
              <TableHead className="hidden text-right lg:table-cell">p50</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {costs.rows.map((r, i) => (
              <TableRow key={`${r.purpose}-${r.model}-${i}`}>
                <TableCell className="font-medium">{humanize(r.purpose)}</TableCell>
                <TableCell className="text-muted-foreground">
                  {r.provider}
                  {r.model ? ` / ${r.model}` : ""}
                </TableCell>
                <TableCell className="text-right tabular">{formatNumber(r.calls)}</TableCell>
                <TableCell className="hidden text-right tabular md:table-cell">
                  {formatTokens(r.input_tokens)} / {formatTokens(r.output_tokens)}
                </TableCell>
                <TableCell className="text-right font-medium tabular">{formatUsd(r.cost_usd)}</TableCell>
                <TableCell className="hidden text-right tabular lg:table-cell">{formatNumber(r.cache_hits)}</TableCell>
                <TableCell className="hidden text-right tabular lg:table-cell">{r.p50_ms != null ? formatMs(r.p50_ms) : "n/a"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Surface>
  );
}

function TeamTable({ days }: { days: number }) {
  const team = useTeamStats(days);
  return (
    <Surface>
      <SurfaceHeader title="Team" description={`Workload now, and what each agent did in the last ${days} days.`} />
      {team.isLoading ? (
        <TableSkeleton rows={3} cols={5} />
      ) : team.isError ? (
        <ErrorState compact error={team.error} onRetry={() => void team.refetch()} />
      ) : !team.data?.length ? (
        <EmptyState compact icon={InboxIcon} title="No agents yet" description="Invite teammates in Settings to share the escalated conversations." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Agent</TableHead>
              <TableHead className="text-right">Open</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Capacity</TableHead>
              <TableHead className="text-right">Resolved</TableHead>
              <TableHead className="hidden text-right md:table-cell">Replies</TableHead>
              <TableHead className="text-right">CSAT</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {team.data.map((r) => (
              <TableRow key={r.id}>
                <TableCell>
                  <span className="flex items-center gap-2.5">
                    <Avatar name={r.name} size="sm" />
                    <span className="font-medium">{r.name}</span>
                    <span className={cn("size-2 rounded-full", r.availability === "online" ? "bg-savings" : "bg-faint")} title={humanize(r.availability)} />
                  </span>
                </TableCell>
                <TableCell className="text-right tabular">{r.open}</TableCell>
                <TableCell className="hidden text-right tabular sm:table-cell">{r.capacity}</TableCell>
                <TableCell className="text-right tabular">{r.resolved}</TableCell>
                <TableCell className="hidden text-right tabular md:table-cell">{r.replies}</TableCell>
                <TableCell className="text-right tabular">{r.csat != null ? r.csat.toFixed(1) : "n/a"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Surface>
  );
}

/** Volume, speed, AI resolution, satisfaction, the team, and what the AI cost. */
export function AnalyticsScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const parsed = Number(params.get("days"));
  const days = (RANGES as readonly number[]).includes(parsed) ? parsed : 30;
  const overview = useOverview(days);
  const costs = useCosts(days);
  const { admin } = usePermissions();
  const [exporting, setExporting] = React.useState(false);
  const o = overview.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Analytics"
        description="How fast customers get answers, how much the AI resolves on its own, how satisfied people are, and what every answer cost."
        actions={
          <>
            <Segmented
              ariaLabel="Period"
              value={String(days)}
              onChange={(v) => router.replace(`${pathname}?days=${v}`, { scroll: false })}
              options={RANGES.map((d) => ({ value: String(d), label: `${d} days` }))}
            />
            {admin && (
              <Button
                variant="outline"
                size="sm"
                disabled={exporting}
                onClick={async () => {
                  setExporting(true);
                  try {
                    await download(`/api/v1/analytics/export.csv?days=${days}`, "supportdesk-daily.csv");
                  } catch (e) {
                    toast.error(errorMessage(e));
                  } finally {
                    setExporting(false);
                  }
                }}
              >
                <DownloadIcon /> CSV
              </Button>
            )}
          </>
        }
      />
      {overview.isError ? (
        <Surface>
          <ErrorState error={overview.error} title="Could not load analytics" onRetry={() => void overview.refetch()} />
        </Surface>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <Stat label="Conversations" icon={InboxIcon} loading={!o} value={formatNumber(o?.totals.created)} detail={o ? `${formatNumber(o.totals.resolved)} resolved` : undefined} />
            <Stat
              label="AI resolution rate"
              icon={BotIcon}
              loading={!o}
              tone="good"
              value={formatRatio(o?.ai_resolution_rate, 0)}
              detail={o ? `${formatNumber(o.totals.ai_resolved)} by the AI alone` : undefined}
            />
            <Stat label="First response" icon={TimerIcon} loading={!o} value={formatDuration(o?.frt_median_s)} detail={o ? `median, p90 ${formatDuration(o.frt_p90_s)}` : undefined} />
            <Stat label="Resolution" icon={ClockIcon} loading={!o} value={formatDuration(o?.resolution_median_s)} detail={o ? `median, p90 ${formatDuration(o.resolution_p90_s)}` : undefined} />
            <Stat
              label="CSAT"
              icon={SmileIcon}
              loading={!o}
              value={o?.csat_avg != null ? `${o.csat_avg.toFixed(1)} / 5` : "n/a"}
              detail={o ? (o.totals.csat_count ? `${formatNumber(o.totals.csat_count)} ratings` : "No ratings yet") : undefined}
            />
            <Stat
              label="Escalation rate"
              icon={ShieldAlertIcon}
              loading={!o}
              tone={o?.escalation_rate != null && o.escalation_rate > 0.5 ? "warn" : "default"}
              value={formatRatio(o?.escalation_rate, 0)}
              detail={o?.human_frt_median_s != null ? `reply after handoff ${formatDuration(o.human_frt_median_s)}` : "handed to a person"}
            />
            <Stat
              label="Deflection"
              icon={ShieldCheckIcon}
              loading={!o}
              tone="good"
              value={formatRatio(o?.deflection_rate, 0)}
              detail="answered without a person"
            />
          </div>

          {o ? <VolumeChart o={o} /> : <Skeleton className="h-80 rounded-2xl" />}

          {o && (
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
              <Breakdown title="By channel" rows={toRows(breakdown(o, "by_channel"))} label={channelLabel} color={CHART.c1} empty="No conversations yet." />
              <Breakdown title="By category" rows={toRows(breakdown(o, "by_category"))} label={(k) => humanize(k)} color={CHART.c5} empty="Triage sets a category on each conversation." />
              <Breakdown title="Escalation reasons" rows={toRows(breakdown(o, "escalation_reasons"))} label={reasonLabel} color={CHART.c4} empty="Nothing was handed over in this period." />
              <Breakdown title="Sentiment" rows={toRows(breakdown(o, "sentiment"))} label={(k) => sentimentSpec(k).label} color={CHART.c3} empty="Sentiment is read from each customer message." />
            </div>
          )}

          <h2 className="pt-2 text-[15px] font-semibold tracking-[-0.01em]">AI and costs</h2>
          {o ? <CostSection o={o} costs={costs.data} /> : <Skeleton className="h-64 rounded-2xl" />}
          <LedgerTable costs={costs.data} loading={costs.isLoading} error={costs.isError ? costs.error : null} retry={() => void costs.refetch()} />
          <TeamTable days={days} />
        </>
      )}
    </div>
  );
}

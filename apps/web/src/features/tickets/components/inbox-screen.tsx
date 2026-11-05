"use client";

import { FilterIcon, InboxIcon, Loader2Icon, SearchIcon, SearchXIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { useNow } from "@/hooks/use-now";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { OnboardingChecklist } from "@/features/onboarding/onboarding-checklist";
import { useUserMap } from "@/features/team/api";
import { errorMessage } from "@/lib/api/errors";
import type { Priority, TicketStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { CHANNELS, PRIORITIES, PRIORITY, STATUS } from "@/lib/labels";

import { useBulkUpdate, useTickets, useViewCounts, type TicketFilters } from "../api";
import { stepSelection, viewSpec, VIEWS } from "../views";

import { Conversation } from "./conversation";
import { TicketRow } from "./ticket-row";

const ANY = "any";

function useFilters() {
  const params = useSearchParams();
  const view = viewSpec(params.get("view"));
  const filters: TicketFilters = {
    view: view.id,
    status: params.get("status") || undefined,
    priority: params.get("priority") || undefined,
    channel: params.get("channel") || undefined,
    q: params.get("q") || undefined,
  };
  return { params, view, filters };
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || !!target.closest("[role=dialog],[role=listbox],[role=menu]");
}

/**
 * The shared inbox: saved views, search and filters, the conversation list (keyset
 * paginated), bulk actions, and the open conversation beside it. The URL holds the view
 * and filters, so a conversation link keeps the list the agent came from.
 */
export function InboxScreen({ selectedId }: { selectedId: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const { params, view, filters } = useFilters();
  const counts = useViewCounts();
  const list = useTickets(filters);
  const users = useUserMap();
  const bulk = useBulkUpdate();
  const { user } = usePermissions();
  const now = useNow(30_000);
  const [search, setSearch] = React.useState(filters.q ?? "");
  const [checked, setChecked] = React.useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = React.useState(!!(filters.status || filters.priority || filters.channel));
  const searchRef = React.useRef<HTMLInputElement>(null);

  const tickets = React.useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const ids = React.useMemo(() => tickets.map((t) => t.id), [tickets]);
  const qs = params.toString();
  const hrefFor = React.useCallback((id: string) => `/inbox/${id}${qs ? `?${qs}` : ""}`, [qs]);

  React.useEffect(() => setSearch(filters.q ?? ""), [filters.q]);
  React.useEffect(() => setChecked(new Set()), [view.id, filters.status, filters.priority, filters.channel, filters.q]);

  function setParam(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v == null || v === "" || v === ANY) next.delete(k);
      else next.set(k, v);
    }
    const s = next.toString();
    router.replace(`${selectedId ? pathname : "/inbox"}${s ? `?${s}` : ""}`, { scroll: false });
  }

  // "#123" opens that conversation when it is the only hit.
  React.useEffect(() => {
    const q = filters.q?.trim();
    if (q && /^#?\d+$/.test(q) && tickets.length === 1 && tickets[0] && tickets[0].id !== selectedId) router.push(hrefFor(tickets[0].id));
  }, [filters.q, tickets, selectedId, router, hrefFor]);

  // Keyboard: j/k move through the list, / focuses search, Escape leaves the conversation.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (e.key === "j" || e.key === "k") {
        const next = stepSelection(ids, selectedId, e.key === "j" ? 1 : -1);
        if (next && next !== selectedId) {
          e.preventDefault();
          router.push(hrefFor(next), { scroll: false });
          requestAnimationFrame(() => document.querySelector(`[data-ticket-id="${next}"]`)?.scrollIntoView({ block: "nearest" }));
        }
      } else if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "Escape" && selectedId) {
        router.push(`/inbox${qs ? `?${qs}` : ""}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ids, selectedId, router, hrefFor, qs]);

  function runBulk(body: { status?: TicketStatus; priority?: Priority; assignee_id?: string; unassign?: boolean }, done: string) {
    const ids = [...checked];
    bulk.mutate(
      { ids, ...body },
      {
        onSuccess: (r) => {
          toast.success(`${done}: ${r.updated} conversation${r.updated === 1 ? "" : "s"}.`);
          setChecked(new Set());
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  const allChecked = tickets.length > 0 && tickets.every((t) => checked.has(t.id));
  const filtered = !!(filters.q || filters.status || filters.priority || filters.channel);

  return (
    <div className="-mb-12 flex h-[calc(100dvh-4.5rem)] min-h-[520px] gap-4 pb-4">
      <section
        aria-label="Conversations"
        className={cn("surface flex min-h-0 w-full flex-col overflow-hidden lg:w-[380px] lg:shrink-0 xl:w-[400px]", selectedId && "hidden lg:flex")}
      >
        <div className="space-y-3 px-3 pt-3">
          <div className="flex items-center gap-2">
            <h1 className="px-1 text-[17px] font-semibold tracking-[-0.02em]">Inbox</h1>
            <form
              className="relative ml-auto flex-1"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                setParam({ q: search.trim() || null });
              }}
            >
              <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-faint" />
              <Input
                ref={searchRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search, or #123"
                aria-label="Search conversations"
                className="h-8 pr-7 pl-8 text-[13px]"
              />
              {search && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => {
                    setSearch("");
                    setParam({ q: null });
                  }}
                  className="absolute top-1/2 right-1.5 flex size-5 -translate-y-1/2 items-center justify-center rounded text-faint hover:text-foreground"
                >
                  <XIcon className="size-3.5" />
                </button>
              )}
            </form>
            <Button
              variant={showFilters ? "secondary" : "subtle"}
              size="icon-sm"
              aria-label="Filters"
              aria-expanded={showFilters}
              onClick={() => setShowFilters((s) => !s)}
            >
              <FilterIcon />
            </Button>
          </div>
          <div role="tablist" aria-label="Views" className="no-scrollbar -mx-3 flex gap-1 overflow-x-auto px-3 pb-0.5">
            {VIEWS.map((v) => {
              const n = v.count ? counts.data?.[v.count] : undefined;
              const active = v.id === view.id;
              return (
                <button
                  key={v.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  title={v.hint}
                  onClick={() => setParam({ view: v.id === "all" ? null : v.id })}
                  className={cn(
                    "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[12.5px] font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                    active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
                  )}
                >
                  {v.label}
                  {n != null && n > 0 && (
                    <span className={cn("tabular text-[11px]", active ? "text-primary-foreground/80" : v.id === "approvals" || v.id === "sla" ? "font-semibold text-warning" : "text-subtle")}>
                      {n}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          {showFilters && (
            <div className="grid grid-cols-3 gap-2">
              <SimpleSelect
                size="sm"
                aria-label="Status"
                value={filters.status ?? ANY}
                onValueChange={(v) => setParam({ status: v })}
                options={[{ value: ANY, label: "Any status" }, ...Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label }))]}
              />
              <SimpleSelect
                size="sm"
                aria-label="Priority"
                value={filters.priority ?? ANY}
                onValueChange={(v) => setParam({ priority: v })}
                options={[{ value: ANY, label: "Any priority" }, ...PRIORITIES.map((p) => ({ value: p, label: PRIORITY[p]?.label ?? p }))]}
              />
              <SimpleSelect
                size="sm"
                aria-label="Channel"
                value={filters.channel ?? ANY}
                onValueChange={(v) => setParam({ channel: v })}
                options={[{ value: ANY, label: "Any channel" }, ...Object.entries(CHANNELS).map(([value, label]) => ({ value, label }))]}
              />
            </div>
          )}
        </div>

        {checked.size > 0 ? (
          <div className="mx-3 mt-3 flex flex-wrap items-center gap-1.5 rounded-xl bg-primary-soft px-2.5 py-2" role="toolbar" aria-label="Bulk actions">
            <span className="mr-auto text-[12.5px] font-semibold text-primary">{checked.size} selected</span>
            {user && (
              <Button size="xs" variant="ghost" disabled={bulk.isPending} onClick={() => runBulk({ assignee_id: user.id }, "Assigned to you")}>
                Assign to me
              </Button>
            )}
            <Button size="xs" variant="ghost" disabled={bulk.isPending} onClick={() => runBulk({ status: "resolved" }, "Resolved")}>
              Resolve
            </Button>
            <SimpleSelect
              size="sm"
              aria-label="Set priority"
              className="h-7 w-[118px] text-xs"
              value=""
              placeholder="Priority"
              onValueChange={(v) => v && runBulk({ priority: v as Priority }, `Priority set to ${PRIORITY[v]?.label.toLowerCase() ?? v}`)}
              options={PRIORITIES.map((p) => ({ value: p, label: PRIORITY[p]?.label ?? p }))}
            />
            <Button size="xs" variant="ghost" disabled={bulk.isPending} onClick={() => runBulk({ unassign: true }, "Unassigned")}>
              Unassign
            </Button>
            <Button size="icon-xs" variant="subtle" aria-label="Clear selection" onClick={() => setChecked(new Set())}>
              <XIcon />
            </Button>
          </div>
        ) : (
          tickets.length > 0 && (
            <div className="flex items-center gap-2 px-6 pt-2.5 pb-0.5 text-[11.5px] text-subtle">
              <input
                type="checkbox"
                checked={allChecked}
                onChange={(e) => setChecked(e.target.checked ? new Set(ids) : new Set())}
                aria-label="Select all loaded conversations"
                className="size-3.5 cursor-pointer accent-[var(--primary)]"
              />
              <span>{view.hint}</span>
              <span className="ml-auto hidden xl:inline">j / k to move</span>
            </div>
          )
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pt-1 pb-3">
          {list.isLoading ? (
            <div className="space-y-2 px-2 pt-2" aria-busy aria-label="Loading conversations">
              {Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="space-y-2 rounded-xl px-2 py-3">
                  <Skeleton className="h-3.5 w-1/3" />
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              ))}
            </div>
          ) : list.isError ? (
            <ErrorState compact error={list.error} title="Could not load conversations" onRetry={() => void list.refetch()} />
          ) : tickets.length === 0 ? (
            filtered ? (
              <EmptyState
                compact
                icon={SearchXIcon}
                title="No conversation matches"
                description="Try other words, a conversation number like #12, or clear the filters."
                action={
                  <Button size="sm" variant="outline" onClick={() => setParam({ q: null, status: null, priority: null, channel: null })}>
                    Clear search and filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                compact
                icon={InboxIcon}
                title={view.empty.title}
                description={view.empty.body}
                action={
                  view.id === "all" ? (
                    <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/settings/inboxes" />}>
                      Install the chat widget
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => setParam({ view: null })}>
                      See all open conversations
                    </Button>
                  )
                }
              />
            )
          ) : (
            <>
              <ul className="space-y-0.5" aria-label={`${view.label} conversations`}>
                {tickets.map((t) => (
                  <TicketRow
                    key={t.id}
                    ticket={t}
                    href={hrefFor(t.id)}
                    selected={t.id === selectedId}
                    checked={checked.has(t.id)}
                    onCheck={(c) =>
                      setChecked((s) => {
                        const n = new Set(s);
                        if (c) n.add(t.id);
                        else n.delete(t.id);
                        return n;
                      })
                    }
                    assignee={t.assignee_id ? users.get(t.assignee_id) : undefined}
                    now={now}
                  />
                ))}
              </ul>
              {list.hasNextPage && (
                <div className="flex justify-center pt-2">
                  <Button size="sm" variant="ghost" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                    {list.isFetchingNextPage ? <Loader2Icon className="animate-spin" /> : null}
                    {list.isFetchingNextPage ? "Loading..." : "Load more"}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      <section aria-label="Conversation" className={cn("min-h-0 min-w-0 flex-1", !selectedId && "hidden lg:block")}>
        {selectedId ? (
          <Conversation
            key={selectedId}
            id={selectedId}
            backHref={`/inbox${qs ? `?${qs}` : ""}`}
            onResolvedNext={() => {
              const next = stepSelection(ids, selectedId, 1);
              if (next && next !== selectedId) router.push(hrefFor(next));
            }}
          />
        ) : (
          <div className="no-scrollbar h-full overflow-y-auto">
            <OnboardingChecklist />
            <div className="surface mt-4 flex min-h-[280px] items-center justify-center">
              <EmptyState
                icon={InboxIcon}
                title="Pick a conversation"
                description="Open one on the left to see the transcript, the AI's decision and its sources, and reply. Use j and k to move, r to reply, e to resolve."
              />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

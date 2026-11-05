"use client";

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useLivePolling } from "@/features/live/agent-live";
import { api, unwrap } from "@/lib/api/client";
import type { BulkPatch, DraftIn, Macro, MacroIn, ReplyIn, SlaPolicyIn, TicketDetail, TicketPatch, TicketQuery } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export type TicketFilters = Omit<TicketQuery, "cursor" | "limit">;

/** Drop empty filters so equal filter sets share one cache entry. */
export function cleanFilters(f: TicketFilters): TicketFilters {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== null && v !== "") out[k] = v;
  return out as TicketFilters;
}

/** One inbox view, keyset paginated: each page carries the cursor of the next. */
export function useTickets(filters: TicketFilters, enabled = true) {
  const poll = useLivePolling();
  const clean = cleanFilters(filters);
  return useInfiniteQuery({
    queryKey: qk.ticketList(clean),
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/tickets", { params: { query: { ...clean, cursor: pageParam ?? undefined, limit: 30 } } })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.live,
    refetchInterval: poll,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useViewCounts() {
  const poll = useLivePolling();
  return useQuery({
    queryKey: qk.counts,
    queryFn: () => unwrap(api.GET("/api/v1/tickets/counts")),
    staleTime: STALE.live,
    refetchInterval: poll === false ? 60_000 : poll,
  });
}

export function useTicket(id: string | null) {
  const poll = useLivePolling();
  return useQuery({
    queryKey: qk.ticket(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/tickets/{ticket_id}", { params: { path: { ticket_id: id ?? "" } } })),
    enabled: !!id,
    staleTime: STALE.live,
    refetchInterval: poll,
  });
}

function useTicketInvalidation() {
  const client = useQueryClient();
  return (detail?: TicketDetail) => {
    if (detail) client.setQueryData(qk.ticket(detail.id), detail);
    void client.invalidateQueries({ queryKey: qk.ticketLists });
    void client.invalidateQueries({ queryKey: qk.counts });
  };
}

export function useUpdateTicket(id: string) {
  const done = useTicketInvalidation();
  return useMutation({
    mutationFn: (body: TicketPatch) => unwrap(api.PATCH("/api/v1/tickets/{ticket_id}", { params: { path: { ticket_id: id } }, body })),
    onSuccess: (detail) => done(detail),
  });
}

export function useReply(id: string) {
  const client = useQueryClient();
  const done = useTicketInvalidation();
  return useMutation({
    mutationFn: (body: ReplyIn) => unwrap(api.POST("/api/v1/tickets/{ticket_id}/messages", { params: { path: { ticket_id: id } }, body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.ticket(id) });
      done();
    },
  });
}

export function useApprove(ticketId: string) {
  const client = useQueryClient();
  const done = useTicketInvalidation();
  return useMutation({
    mutationFn: ({ messageId, body }: { messageId: string; body?: string | null }) =>
      unwrap(api.POST("/api/v1/messages/{message_id}/approve", { params: { path: { message_id: messageId } }, body: { body: body ?? null } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.ticket(ticketId) });
      done();
    },
  });
}

export function useReject(ticketId: string) {
  const client = useQueryClient();
  const done = useTicketInvalidation();
  return useMutation({
    mutationFn: (messageId: string) => unwrap(api.POST("/api/v1/messages/{message_id}/reject", { params: { path: { message_id: messageId } } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.ticket(ticketId) });
      done();
    },
  });
}

/** Approve straight from a list (approvals queue), knowing only the ticket. */
export function useApproveAny() {
  const client = useQueryClient();
  const done = useTicketInvalidation();
  return useMutation({
    mutationFn: ({ messageId }: { messageId: string; ticketId: string }) =>
      unwrap(api.POST("/api/v1/messages/{message_id}/approve", { params: { path: { message_id: messageId } }, body: { body: null } })),
    onSuccess: (_m, vars) => {
      void client.invalidateQueries({ queryKey: qk.ticket(vars.ticketId) });
      done();
    },
  });
}

export function useDraft(id: string) {
  return useMutation({
    mutationFn: (body: DraftIn) => unwrap(api.POST("/api/v1/tickets/{ticket_id}/draft", { params: { path: { ticket_id: id } }, body })),
  });
}

export function useBulkUpdate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: BulkPatch) => unwrap(api.POST("/api/v1/tickets/bulk", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.tickets }),
  });
}

export function useMacros() {
  return useQuery({ queryKey: qk.macros, queryFn: () => unwrap(api.GET("/api/v1/macros")), staleTime: STALE.config });
}

export function useSaveMacro() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: MacroIn }): Promise<Macro> =>
      id
        ? unwrap(api.PUT("/api/v1/macros/{macro_id}", { params: { path: { macro_id: id } }, body }))
        : unwrap(api.POST("/api/v1/macros", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.macros }),
  });
}

export function useDeleteMacro() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/macros/{macro_id}", { params: { path: { macro_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.macros }),
  });
}

export function useSlaPolicies() {
  return useQuery({ queryKey: qk.slaPolicies, queryFn: () => unwrap(api.GET("/api/v1/sla-policies")), staleTime: STALE.config });
}

export function useSaveSlaPolicies() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SlaPolicyIn[]) => unwrap(api.PUT("/api/v1/sla-policies", { body })),
    onSuccess: (data) => client.setQueryData(qk.slaPolicies, data),
  });
}

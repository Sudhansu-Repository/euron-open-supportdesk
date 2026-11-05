"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { publicApi, unwrap } from "@/lib/api/client";
import type { WidgetConversation } from "@/lib/api/types";
import { qk } from "@/lib/query-keys";

import { waiting } from "./state";

/**
 * Widget calls run on this app's origin (the frame is ours), through the same /api
 * rewrite as the agent app, authenticated by the visitor token as a bearer header.
 */
export function startSession(
  key: string,
  body: { token: string | null; parent_origin: string | null; external_id?: string | null; signature?: string | null; email?: string | null; name?: string | null },
) {
  return unwrap(publicApi(null).POST("/api/v1/widget/{public_key}/session", { params: { path: { public_key: key } }, body }));
}

/** The conversation, polled every 3 s while waiting on the AI or a person and the socket is down. */
export function useWidgetConversation(token: string | null, ticketId: string | null, socketOpen: boolean) {
  return useQuery({
    queryKey: qk.widgetConversation(ticketId ?? ""),
    queryFn: () => unwrap(publicApi(token).GET("/api/v1/widget/tickets/{ticket_id}", { params: { path: { ticket_id: ticketId ?? "" } } })),
    enabled: !!token && !!ticketId,
    refetchInterval: (q) => (!socketOpen && waiting(q.state.data) ? 3000 : socketOpen ? false : 15_000),
    retry: 1,
  });
}

function useSetConversation() {
  const client = useQueryClient();
  return (c: WidgetConversation) => client.setQueryData(qk.widgetConversation(c.ticket_id), c);
}

export function useWidgetSend(token: string | null) {
  const set = useSetConversation();
  return useMutation({
    mutationFn: (body: { body: string; ticket_id: string | null }) => unwrap(publicApi(token).POST("/api/v1/widget/messages", { body })),
    onSuccess: set,
  });
}

export function useWidgetHuman(token: string | null) {
  const set = useSetConversation();
  return useMutation({
    mutationFn: (ticketId: string) => unwrap(publicApi(token).POST("/api/v1/widget/tickets/{ticket_id}/human", { params: { path: { ticket_id: ticketId } } })),
    onSuccess: set,
  });
}

export function useWidgetFeedback(token: string | null) {
  return useMutation({
    mutationFn: ({ messageId, helpful }: { messageId: string; helpful: boolean }) =>
      unwrap(publicApi(token).POST("/api/v1/widget/messages/{message_id}/feedback", { params: { path: { message_id: messageId } }, body: { helpful } })),
  });
}

export function useWidgetRating(token: string | null) {
  return useMutation({
    mutationFn: ({ ticketId, score, comment }: { ticketId: string; score: number; comment?: string }) =>
      unwrap(publicApi(token).POST("/api/v1/widget/tickets/{ticket_id}/rating", { params: { path: { ticket_id: ticketId } }, body: { score, comment: comment || null } })),
  });
}

export function useWidgetEmail(token: string | null) {
  return useMutation({
    mutationFn: (body: { email: string; name?: string | null }) => unwrap(publicApi(token).POST("/api/v1/widget/email", { body })),
  });
}

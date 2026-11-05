"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { publicApi, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

import { readPortalToken, writePortalToken } from "./token";

/** The customer's portal token for this help center, kept in localStorage. */
export function usePortalToken(slug: string): { token: string | null; ready: boolean; set: (t: string | null) => void } {
  const [token, setToken] = React.useState<string | null>(null);
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    setToken(readPortalToken(slug));
    setReady(true);
  }, [slug]);
  const set = React.useCallback(
    (t: string | null) => {
      writePortalToken(slug, t);
      setToken(t);
    },
    [slug],
  );
  return { token, ready, set };
}

export function useRequestLink(slug: string) {
  return useMutation({ mutationFn: (email: string) => unwrap(publicApi(null).POST("/api/v1/portal/{slug}/link", { params: { path: { slug } }, body: { email } })) });
}

export function useRedeemLink(slug: string) {
  return useMutation({ mutationFn: (token: string) => unwrap(publicApi(null).POST("/api/v1/portal/{slug}/session", { params: { path: { slug } }, body: { token } })) });
}

export function usePortalTickets(slug: string, token: string | null) {
  return useQuery({
    queryKey: qk.portalTickets(slug),
    queryFn: () => unwrap(publicApi(token).GET("/api/v1/portal/{slug}/tickets", { params: { path: { slug } } })),
    enabled: !!token,
    staleTime: STALE.list,
    retry: false,
  });
}

export function usePortalTicket(slug: string, token: string | null, id: string, poll: number | false) {
  return useQuery({
    queryKey: qk.portalTicket(slug, id),
    queryFn: () => unwrap(publicApi(token).GET("/api/v1/portal/{slug}/tickets/{ticket_id}", { params: { path: { slug, ticket_id: id } } })),
    enabled: !!token,
    refetchInterval: poll,
    retry: false,
  });
}

export function useCreatePortalTicket(slug: string, token: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { subject: string; body: string }) => unwrap(publicApi(token).POST("/api/v1/portal/{slug}/tickets", { params: { path: { slug } }, body })),
    onSuccess: (t) => {
      client.setQueryData(qk.portalTicket(slug, t.id), t);
      void client.invalidateQueries({ queryKey: qk.portalTickets(slug) });
    },
  });
}

export function usePortalReply(slug: string, token: string | null, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => unwrap(publicApi(token).POST("/api/v1/portal/{slug}/tickets/{ticket_id}/messages", { params: { path: { slug, ticket_id: id } }, body: { body } })),
    onSuccess: (t) => client.setQueryData(qk.portalTicket(slug, id), t),
  });
}

export function usePortalFeedback(slug: string, token: string | null) {
  return useMutation({
    mutationFn: ({ messageId, helpful }: { messageId: string; helpful: boolean }) =>
      unwrap(publicApi(token).POST("/api/v1/portal/{slug}/messages/{message_id}/feedback", { params: { path: { slug, message_id: messageId } }, body: { helpful } })),
  });
}

export function usePortalRating(slug: string, token: string | null, id: string) {
  return useMutation({
    mutationFn: ({ score, comment }: { score: number; comment?: string }) =>
      unwrap(publicApi(token).POST("/api/v1/portal/{slug}/tickets/{ticket_id}/rating", { params: { path: { slug, ticket_id: id } }, body: { score, comment: comment || null } })),
  });
}

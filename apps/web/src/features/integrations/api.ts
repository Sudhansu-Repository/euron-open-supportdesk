"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { WebhookPatch } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useApiKeys() {
  return useQuery({ queryKey: qk.apiKeys, queryFn: () => unwrap(api.GET("/api/v1/api-keys")), staleTime: STALE.list });
}

export function useCreateApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; scope: "read" | "write" }) => unwrap(api.POST("/api/v1/api-keys", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.apiKeys }),
  });
}

export function useRevokeApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/api-keys/{key_id}", { params: { path: { key_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.apiKeys }),
  });
}

export function useWebhooks() {
  return useQuery({ queryKey: qk.webhooks, queryFn: () => unwrap(api.GET("/api/v1/webhooks")), staleTime: STALE.list });
}

export function useWebhookEvents() {
  return useQuery({ queryKey: qk.webhookEvents, queryFn: () => unwrap(api.GET("/api/v1/webhooks/events")), staleTime: STALE.static });
}

export function useCreateWebhook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { url: string; events: string[] }) => unwrap(api.POST("/api/v1/webhooks", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.webhooks }),
  });
}

export function useUpdateWebhook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WebhookPatch }) =>
      unwrap(api.PATCH("/api/v1/webhooks/{webhook_id}", { params: { path: { webhook_id: id } }, body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.webhooks }),
  });
}

export function useDeleteWebhook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/webhooks/{webhook_id}", { params: { path: { webhook_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.webhooks }),
  });
}

export function useTestWebhook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/webhooks/{webhook_id}/test", { params: { path: { webhook_id: id } } })),
    onSuccess: (_d, id) => {
      setTimeout(() => void client.invalidateQueries({ queryKey: qk.deliveries(id) }), 1500);
      void client.invalidateQueries({ queryKey: qk.webhooks });
    },
  });
}

export function useDeliveries(id: string | null) {
  return useQuery({
    queryKey: qk.deliveries(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/webhooks/{webhook_id}/deliveries", { params: { path: { webhook_id: id ?? "" } } })),
    enabled: !!id,
    refetchInterval: 5000,
  });
}

export function useAudit(action: string) {
  return useInfiniteQuery({
    queryKey: qk.audit(action),
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/audit", { params: { query: { cursor: pageParam ?? undefined, limit: 50, action: action || undefined } } })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.list,
  });
}

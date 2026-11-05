"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { InboxPatch, PriceIn, SettingsPatch } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useSettings() {
  return useQuery({ queryKey: qk.settings, queryFn: () => unwrap(api.GET("/api/v1/org/settings")), staleTime: STALE.config });
}

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsPatch) => unwrap(api.PATCH("/api/v1/org/settings", { body })),
    onSuccess: (data) => {
      client.setQueryData(qk.settings, data);
      void client.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useTestAi() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/org/ai/test")) });
}

export function usePrices() {
  return useQuery({ queryKey: qk.prices, queryFn: () => unwrap(api.GET("/api/v1/org/prices")), staleTime: STALE.config });
}

export function useSavePrice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PriceIn) => unwrap(api.PUT("/api/v1/org/prices", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.prices }),
  });
}

export function useDeletePrice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/org/prices/{price_id}", { params: { path: { price_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.prices }),
  });
}

export function useInboxes() {
  return useQuery({ queryKey: qk.inboxes, queryFn: () => unwrap(api.GET("/api/v1/inboxes")), staleTime: STALE.config });
}

export function useUpdateInbox() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InboxPatch }) => unwrap(api.PATCH("/api/v1/inboxes/{inbox_id}", { params: { path: { inbox_id: id } }, body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.inboxes }),
  });
}

export function useCreateInbox() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; channel: string }) => unwrap(api.POST("/api/v1/inboxes", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.inboxes }),
  });
}

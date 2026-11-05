"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useGaps(status: string) {
  return useQuery({
    queryKey: qk.gapList(status),
    queryFn: () => unwrap(api.GET("/api/v1/gaps", { params: { query: { status: status || undefined } } })),
    staleTime: STALE.list,
  });
}

export function useGap(id: string | null) {
  return useQuery({
    queryKey: qk.gap(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/gaps/{gap_id}", { params: { path: { gap_id: id ?? "" } } })),
    enabled: !!id,
  });
}

export function useDraftFromGap() {
  return useMutation({ mutationFn: (id: string) => unwrap(api.POST("/api/v1/gaps/{gap_id}/draft", { params: { path: { gap_id: id } } })) });
}

export function useSetGapStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "open" | "dismissed" }) =>
      unwrap(api.POST("/api/v1/gaps/{gap_id}/status", { params: { path: { gap_id: id } }, body: { status } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.gaps }),
  });
}

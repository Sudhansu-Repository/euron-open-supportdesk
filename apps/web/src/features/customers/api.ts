"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { CustomerPatch } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useCustomers(q: string, vip: boolean) {
  return useQuery({
    queryKey: qk.customerList({ q, vip }),
    queryFn: () => unwrap(api.GET("/api/v1/customers", { params: { query: { q: q || undefined, vip: vip || undefined, limit: 100 } } })),
    staleTime: STALE.list,
    placeholderData: keepPreviousData,
  });
}

export function useCustomer(id: string | null) {
  return useQuery({
    queryKey: qk.customer(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/customers/{customer_id}", { params: { path: { customer_id: id ?? "" } } })),
    enabled: !!id,
    staleTime: STALE.list,
  });
}

export function useUpdateCustomer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CustomerPatch }) =>
      unwrap(api.PATCH("/api/v1/customers/{customer_id}", { params: { path: { customer_id: id } }, body })),
    onSuccess: (_c, vars) => {
      void client.invalidateQueries({ queryKey: qk.customers });
      void client.invalidateQueries({ queryKey: qk.customer(vars.id) });
      void client.invalidateQueries({ queryKey: qk.tickets });
    },
  });
}

export function useMergeCustomers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { keep_id: string; drop_id: string }) => unwrap(api.POST("/api/v1/customers/merge", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.customers });
      void client.invalidateQueries({ queryKey: qk.tickets });
    },
  });
}

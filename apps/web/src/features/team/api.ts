"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { InviteIn, TeamIn, User, UserPatch } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useUsers() {
  return useQuery({ queryKey: qk.users, queryFn: () => unwrap(api.GET("/api/v1/users")), staleTime: STALE.list });
}

/** Agents by id, for avatars and names in lists. */
export function useUserMap(): Map<string, User> {
  const users = useUsers();
  return new Map((users.data ?? []).map((u) => [u.id, u]));
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserPatch }) => unwrap(api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.users }),
  });
}

export function useInvitations(enabled = true) {
  return useQuery({ queryKey: qk.invitations, queryFn: () => unwrap(api.GET("/api/v1/invitations")), staleTime: STALE.list, enabled });
}

export function useInvite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: InviteIn) => unwrap(api.POST("/api/v1/invitations", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.invitations }),
  });
}

export function useRevokeInvitation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.invitations }),
  });
}

export function useTeams() {
  return useQuery({ queryKey: qk.teams, queryFn: () => unwrap(api.GET("/api/v1/org/teams")), staleTime: STALE.config });
}

export function useSaveTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: TeamIn }) =>
      id ? unwrap(api.PUT("/api/v1/org/teams/{team_id}", { params: { path: { team_id: id } }, body })) : unwrap(api.POST("/api/v1/org/teams", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.teams }),
  });
}

export function useDeleteTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/org/teams/{team_id}", { params: { path: { team_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.teams }),
  });
}

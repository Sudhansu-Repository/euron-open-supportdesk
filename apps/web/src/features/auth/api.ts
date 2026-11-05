"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Availability, Session, User } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { isAdmin, isOwner } from "@/lib/roles";

/**
 * The session: the signed-in agent and their organisation, or a null user. The session
 * endpoint answers signed-out visitors with 200 and no user instead of a 401.
 */
export function useSession() {
  return useQuery({
    queryKey: qk.me,
    queryFn: (): Promise<Session> => unwrap(api.GET("/api/v1/auth/session")),
    staleTime: STALE.static,
    retry: false,
  });
}

export function useMe(): { data: User | null | undefined; isError: boolean; error: unknown; refetch: () => void } {
  const s = useSession();
  return { data: s.data === undefined ? undefined : (s.data.user ?? null), isError: s.isError, error: s.error, refetch: () => void s.refetch() };
}

/** Role flags for the current agent. While loading, nothing privileged is shown. */
export function usePermissions(): { user: User | null | undefined; signedIn: boolean; admin: boolean; owner: boolean } {
  const { data } = useMe();
  return { user: data, signedIn: !!data, admin: isAdmin(data?.role), owner: isOwner(data?.role) };
}

function useSignedIn() {
  const client = useQueryClient();
  return (session: { user: User; org_slug: string }) => {
    client.clear();
    client.setQueryData<Session>(qk.me, { user: session.user, org_slug: session.org_slug });
    void client.invalidateQueries({ queryKey: qk.me });
  };
}

export function useLogin() {
  const signedIn = useSignedIn();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => unwrap(api.POST("/api/v1/auth/login", { body })),
    onSuccess: signedIn,
  });
}

/** Whether this server lets new organisations sign up. */
export function useSignupStatus() {
  return useQuery({
    queryKey: qk.signupStatus,
    queryFn: () => unwrap(api.GET("/api/v1/auth/signup")),
    staleTime: STALE.config,
    retry: false,
  });
}

export function useSignup() {
  const signedIn = useSignedIn();
  return useMutation({
    mutationFn: (body: { org_name: string; name: string; email: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/signup", { body })),
    onSuccess: signedIn,
  });
}

export function useInvitationPreview(token: string | null) {
  return useQuery({
    queryKey: qk.invitation(token ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/auth/invitations/{token}", { params: { path: { token: token ?? "" } } })),
    enabled: !!token,
    retry: false,
  });
}

export function useAcceptInvitation() {
  const signedIn = useSignedIn();
  return useMutation({
    mutationFn: (body: { token: string; name: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/invitations/accept", { body })),
    onSuccess: signedIn,
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    onSettled: () => client.clear(),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) => unwrap(api.POST("/api/v1/auth/password", { body })),
    onSuccess: (session) => client.setQueryData<Session>(qk.me, (old) => ({ ...(old ?? {}), user: session.user })),
  });
}

/** Online or away: routing only assigns new conversations to online agents. */
export function useSetAvailability() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (availability: Availability) => unwrap(api.PATCH("/api/v1/me", { body: { availability } })),
    onMutate: async (availability) => {
      await client.cancelQueries({ queryKey: qk.me });
      const previous = client.getQueryData<Session>(qk.me);
      if (previous?.user) client.setQueryData<Session>(qk.me, { ...previous, user: { ...previous.user, availability } });
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) client.setQueryData(qk.me, ctx.previous);
    },
    onSuccess: (user) => {
      client.setQueryData<Session>(qk.me, (old) => ({ ...(old ?? {}), user }));
      void client.invalidateQueries({ queryKey: qk.users });
    },
  });
}

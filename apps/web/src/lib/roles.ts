import type { Role } from "./api/types";

export const ROLES: readonly Role[] = ["owner", "admin", "agent"] as const;

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", agent: "Agent" };

const ROLE_DESCRIPTION: Record<Role, string> = {
  owner: "Everything an admin can do, plus owning the organisation.",
  admin: "Settings, knowledge, AI policy, team, integrations and the audit log.",
  agent: "Works the inbox: replies, notes, approvals, customers.",
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

export function roleLabel(role: string | null | undefined): string {
  return isRole(role) ? ROLE_LABEL[role] : "Unknown";
}

export function roleDescription(role: string | null | undefined): string {
  return isRole(role) ? ROLE_DESCRIPTION[role] : "";
}

/** Admins and owners change settings, knowledge and integrations. */
export function isAdmin(role: string | null | undefined): boolean {
  return role === "admin" || role === "owner";
}

export function isOwner(role: string | null | undefined): boolean {
  return role === "owner";
}

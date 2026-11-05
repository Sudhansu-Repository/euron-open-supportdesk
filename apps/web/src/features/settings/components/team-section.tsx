"use client";

import { MailPlusIcon, PlusIcon, Trash2Icon, UsersRoundIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Avatar } from "@/components/avatar";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { useDeleteTeam, useInvitations, useInvite, useRevokeInvitation, useSaveTeam, useTeams, useUpdateUser, useUsers } from "@/features/team/api";
import { errorMessage } from "@/lib/api/errors";
import type { Role, Team } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";
import { humanize } from "@/lib/labels";
import { roleDescription, roleLabel } from "@/lib/roles";

import { Card } from "./shared";

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const invite = useInvite();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<"agent" | "admin">("agent");
  const [link, setLink] = React.useState<{ email: string; url: string } | null>(null);
  React.useEffect(() => {
    if (!open) setLink(null);
  }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a teammate</DialogTitle>
          <DialogDescription>They get an email with a link to choose their name and password. The link expires after a few days.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            invite.mutate(
              { email: email.trim(), role },
              {
                onSuccess: (inv) => {
                  toast.success(`Invitation sent to ${inv.email}.`);
                  setLink({ email: inv.email, url: inv.invite_url });
                  setEmail("");
                },
                onError: (err) => toast.error(errorMessage(err)),
              },
            );
          }}
        >
          <DialogBody className="space-y-4">
            {link && (
              <div role="status" className="rounded-xl bg-primary-soft px-4 py-3">
                <div className="text-[12.5px] font-semibold text-primary">Invited {link.email}. Share this link if email is not set up yet</div>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate rounded-lg bg-card px-3 py-2 font-mono text-[12px] shadow-[var(--elev-1)]">{link.url}</code>
                  <CopyButton value={link.url} />
                </div>
                <p className="mt-1.5 text-[11.5px] text-muted-foreground">It is shown only now. It works once and expires with the invitation.</p>
              </div>
            )}
            <Field label="Email" htmlFor="inv-email">
              <Input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" autoFocus />
            </Field>
            <Field label="Role" htmlFor="inv-role" hint={roleDescription(role)}>
              <SimpleSelect id="inv-role" value={role} onValueChange={(v) => setRole(v as "agent" | "admin")} options={[{ value: "agent", label: "Agent" }, { value: "admin", label: "Admin" }]} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{link ? "Done" : "Cancel"}</Button>
            <Button type="submit" disabled={invite.isPending || !email.trim()}>{invite.isPending ? "Sending..." : link ? "Invite another" : "Send invitation"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TeamDialog({ team, open, onOpenChange }: { team: Team | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const users = useUsers();
  const save = useSaveTeam();
  const [name, setName] = React.useState("");
  const [members, setMembers] = React.useState<string[]>([]);
  React.useEffect(() => {
    if (open) {
      setName(team?.name ?? "");
      setMembers(team?.member_ids ?? []);
    }
  }, [open, team]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{team ? `Edit ${team.name}` : "New team"}</DialogTitle>
          <DialogDescription>Conversations routed to a team go round-robin to its online members with spare capacity.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              { id: team?.id, body: { name: name.trim(), member_ids: members } },
              { onSuccess: () => { toast.success("Team saved."); onOpenChange(false); }, onError: (err) => toast.error(errorMessage(err)) },
            );
          }}
        >
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="t-name"><Input id="t-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Billing" /></Field>
            <div>
              <div className="mb-1.5 text-[13px] font-medium">Members</div>
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {(users.data ?? []).map((u) => (
                  <li key={u.id}>
                    <label className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] hover:bg-muted">
                      <input type="checkbox" className="size-3.5 accent-[var(--primary)]" checked={members.includes(u.id)} onChange={(e) => setMembers((m) => (e.target.checked ? [...m, u.id] : m.filter((x) => x !== u.id)))} />
                      <Avatar name={u.name} size="xs" /> {u.name} <span className="text-subtle">{u.email}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={save.isPending || !name.trim()}>{save.isPending ? "Saving..." : "Save team"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TeamSection() {
  const users = useUsers();
  const invitations = useInvitations();
  const teams = useTeams();
  const updateUser = useUpdateUser();
  const revoke = useRevokeInvitation();
  const removeTeam = useDeleteTeam();
  const { user: me, owner } = usePermissions();
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [teamOpen, setTeamOpen] = React.useState(false);
  const [editTeam, setEditTeam] = React.useState<Team | null>(null);
  const [deleteTeam, setDeleteTeam] = React.useState<Team | null>(null);
  const names = new Map((users.data ?? []).map((u) => [u.id, u.name]));
  const pending = (invitations.data ?? []).filter((i) => !i.accepted_at);

  function patchUser(id: string, body: { role?: Role; disabled?: boolean; capacity?: number }, done: string) {
    updateUser.mutate({ id, body }, { onSuccess: () => toast.success(done), onError: (e) => toast.error(errorMessage(e)) });
  }

  return (
    <div className="space-y-5">
      <Card
        title="Agents"
        description="Capacity is how many open conversations routing gives an agent at once. Away agents keep theirs but get no new ones."
        action={<Button size="sm" onClick={() => setInviteOpen(true)}><MailPlusIcon /> Invite</Button>}
      >
        {users.isLoading ? (
          <TableSkeleton rows={3} cols={4} />
        ) : users.isError ? (
          <ErrorState compact error={users.error} onRetry={() => void users.refetch()} />
        ) : (
          <div className="-mx-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="w-28">Capacity</TableHead>
                  <TableHead className="hidden md:table-cell">Last seen</TableHead>
                  <TableHead className="text-right">Active</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(users.data ?? []).map((u) => {
                  const self = u.id === me?.id;
                  const lockRole = self || (u.role === "owner" && !owner);
                  return (
                    <TableRow key={u.id} className={u.disabled ? "opacity-60" : undefined}>
                      <TableCell>
                        <span className="flex items-center gap-2.5">
                          <Avatar name={u.name} size="sm" />
                          <span className="min-w-0">
                            <span className="flex items-center gap-1.5 font-medium">
                              {u.name} {self && <Chip tone="primary">You</Chip>}
                              <span className={u.availability === "online" ? "size-2 rounded-full bg-savings" : "size-2 rounded-full bg-faint"} title={humanize(u.availability)} />
                            </span>
                            <span className="block truncate text-[12px] text-muted-foreground">{u.email}</span>
                          </span>
                        </span>
                      </TableCell>
                      <TableCell className="w-36">
                        {lockRole ? (
                          <Chip tone="neutral">{roleLabel(u.role)}</Chip>
                        ) : (
                          <SimpleSelect
                            size="sm"
                            aria-label={`Role of ${u.name}`}
                            value={u.role}
                            onValueChange={(v) => v !== u.role && patchUser(u.id, { role: v as Role }, `${u.name} is now ${roleLabel(v).toLowerCase()}.`)}
                            options={[{ value: "agent", label: "Agent" }, { value: "admin", label: "Admin" }, ...(owner ? [{ value: "owner", label: "Owner" }] : [])]}
                          />
                        )}
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          min={0}
                          max={100}
                          aria-label={`Capacity of ${u.name}`}
                          defaultValue={u.capacity}
                          className="h-8 w-20"
                          onBlur={(e) => {
                            const n = Number(e.target.value);
                            if (Number.isFinite(n) && n !== u.capacity) patchUser(u.id, { capacity: n }, `Capacity of ${u.name} set to ${n}.`);
                          }}
                        />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">{formatRelative(u.last_seen_at)}</TableCell>
                      <TableCell className="text-right">
                        <Switch
                          aria-label={u.disabled ? `Enable ${u.name}` : `Disable ${u.name}`}
                          checked={!u.disabled}
                          disabled={self || updateUser.isPending}
                          onCheckedChange={(on) => patchUser(u.id, { disabled: !on }, on ? `${u.name} can sign in again.` : `${u.name} is disabled and signed out.`)}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      <Card title="Pending invitations" description="Invitations not accepted yet. Revoke one to cancel its link.">
        {invitations.isLoading ? (
          <TableSkeleton rows={2} cols={3} />
        ) : invitations.isError ? (
          <ErrorState compact error={invitations.error} onRetry={() => void invitations.refetch()} />
        ) : pending.length === 0 ? (
          <EmptyState compact icon={MailPlusIcon} title="No pending invitations" description="Escalated conversations need people. Invite the teammates who answer customers today." action={<Button size="sm" variant="outline" onClick={() => setInviteOpen(true)}>Invite a teammate</Button>} />
        ) : (
          <ul className="space-y-1.5">
            {pending.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-muted/60 px-3 py-2 text-[13px]">
                <span className="min-w-0 flex-1 truncate font-medium">{i.email}</span>
                <Chip tone="neutral">{roleLabel(i.role)}</Chip>
                <span className="text-[12px] text-subtle">expires {formatRelative(i.expires_at)}</span>
                <Button size="xs" variant="ghost" disabled={revoke.isPending} onClick={() => revoke.mutate(i.id, { onSuccess: () => toast.success("Invitation revoked."), onError: (e) => toast.error(errorMessage(e)) })}>
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[12px] text-muted-foreground">
          Teammates accept from the link in their email (<code className="rounded bg-muted px-1 font-mono">/invite?token=...</code>), where they choose their name and password.
        </p>
      </Card>

      <Card title="Teams" description="Group agents (Billing, Technical) so routing and reports can follow them." action={<Button size="sm" variant="outline" onClick={() => { setEditTeam(null); setTeamOpen(true); }}><PlusIcon /> New team</Button>}>
        {teams.isLoading ? (
          <TableSkeleton rows={2} cols={2} />
        ) : teams.isError ? (
          <ErrorState compact error={teams.error} onRetry={() => void teams.refetch()} />
        ) : !teams.data?.length ? (
          <EmptyState compact icon={UsersRoundIcon} title="No teams" description="Without teams, routing shares conversations among every online agent. Add teams when you specialise." />
        ) : (
          <ul className="space-y-1.5">
            {teams.data.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
                <span className="font-semibold">{t.name}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{t.member_ids.map((id) => names.get(id) ?? "Unknown").join(", ") || "No members"}</span>
                <Button size="xs" variant="ghost" onClick={() => { setEditTeam(t); setTeamOpen(true); }}>Edit</Button>
                <Button size="icon-xs" variant="subtle" aria-label={`Delete ${t.name}`} onClick={() => setDeleteTeam(t)}><Trash2Icon /></Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      <TeamDialog team={editTeam} open={teamOpen} onOpenChange={setTeamOpen} />
      <ConfirmDialog
        open={!!deleteTeam}
        onOpenChange={(o) => !o && setDeleteTeam(null)}
        title={`Delete ${deleteTeam?.name ?? "team"}?`}
        description="Its conversations keep their assignee; the team is cleared from them."
        confirmLabel="Delete team"
        pending={removeTeam.isPending}
        onConfirm={() => deleteTeam && removeTeam.mutate(deleteTeam.id, { onSuccess: () => { toast.success("Team deleted."); setDeleteTeam(null); }, onError: (e) => toast.error(errorMessage(e)) })}
      />
    </div>
  );
}

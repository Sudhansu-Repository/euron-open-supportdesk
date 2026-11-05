"use client";

import { KeyRoundIcon, PlusIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Segmented } from "@/components/segmented";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/features/integrations/api";
import { errorMessage } from "@/lib/api/errors";
import type { ApiKey } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";

import { Card, SecretOnce } from "./shared";

export function ApiKeysSection() {
  const keys = useApiKeys();
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();
  const [name, setName] = React.useState("");
  const [scope, setScope] = React.useState<"read" | "write">("read");
  const [secret, setSecret] = React.useState<string | null>(null);
  const [del, setDel] = React.useState<ApiKey | null>(null);
  const active = (keys.data ?? []).filter((k) => !k.revoked_at);
  const revoked = (keys.data ?? []).filter((k) => k.revoked_at);

  return (
    <div className="space-y-5">
      <Card title="Create a key" description="For your own systems calling the REST API: create tickets, read conversations, sync articles. Send it as Authorization: Bearer <key>.">
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-center"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ name: name.trim(), scope }, { onSuccess: (k) => { setSecret(k.key); setName(""); toast.success("Key created."); }, onError: (err) => toast.error(errorMessage(err)) });
          }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, like CRM sync" aria-label="Key name" required className="sm:max-w-xs" />
          <Segmented ariaLabel="Scope" value={scope} onChange={setScope} className="sm:w-56" options={[{ value: "read", label: "Read" }, { value: "write", label: "Read and write" }]} />
          <Button type="submit" disabled={create.isPending || !name.trim()}><PlusIcon /> Create key</Button>
        </form>
        {secret && <div className="mt-4"><SecretOnce label="Your new API key" value={secret} onDone={() => setSecret(null)} /></div>}
      </Card>
      <Card title="Keys" description="Only a prefix is stored in readable form; the key itself is hashed.">
        {keys.isLoading ? (
          <TableSkeleton rows={3} cols={4} />
        ) : keys.isError ? (
          <ErrorState compact error={keys.error} onRetry={() => void keys.refetch()} />
        ) : !keys.data?.length ? (
          <EmptyState compact icon={KeyRoundIcon} title="No API keys" description="Create a read key to pull conversations into your data warehouse, or a write key to open tickets from your app." />
        ) : (
          <div className="-mx-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead className="hidden sm:table-cell">Last used</TableHead>
                  <TableHead className="hidden md:table-cell">Created</TableHead>
                  <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...active, ...revoked].map((k) => (
                  <TableRow key={k.id} className={k.revoked_at ? "opacity-55" : undefined}>
                    <TableCell>
                      <span className="font-medium">{k.name}</span> <code className="ml-1 font-mono text-[12px] text-muted-foreground">{k.prefix}...</code>
                    </TableCell>
                    <TableCell><Chip tone={k.scope === "write" ? "warning" : "info"}>{k.scope === "write" ? "Read and write" : "Read"}</Chip></TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">{k.last_used_at ? formatRelative(k.last_used_at) : "Never"}</TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">{formatRelative(k.created_at)}</TableCell>
                    <TableCell className="text-right">
                      {k.revoked_at ? <Chip tone="neutral">Revoked</Chip> : <Button size="xs" variant="destructive-soft" onClick={() => setDel(k)}>Revoke</Button>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
      <ConfirmDialog
        open={!!del}
        onOpenChange={(o) => !o && setDel(null)}
        title={`Revoke ${del?.name ?? "this key"}?`}
        description="Requests with this key fail from now on. This cannot be undone; create a new key if you need one."
        confirmLabel="Revoke key"
        pending={revoke.isPending}
        onConfirm={() => del && revoke.mutate(del.id, { onSuccess: () => { toast.success("Key revoked."); setDel(null); }, onError: (e) => toast.error(errorMessage(e)) })}
      />
    </div>
  );
}

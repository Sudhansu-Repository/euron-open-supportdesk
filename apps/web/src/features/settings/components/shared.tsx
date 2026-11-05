"use client";

import { KeyRoundIcon, ShieldIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/** A settings card: title, explanation, body, and an optional footer with the save button. */
export function Card({
  title,
  description,
  children,
  footer,
  action,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <Surface className={cn("overflow-hidden", className)}>
      <SurfaceHeader title={title} description={description} action={action} />
      <div className="px-5 pb-5">{children}</div>
      {footer && <div className="flex flex-wrap items-center justify-end gap-2 bg-muted/40 px-5 py-3">{footer}</div>}
    </Surface>
  );
}

/** Save and reset for a form whose state lives locally until saved. */
export function SaveFooter({ dirty, pending, onReset, onSave, label = "Save changes" }: { dirty: boolean; pending: boolean; onReset: () => void; onSave: () => void; label?: string }) {
  return (
    <>
      {dirty && <span className="mr-auto text-[12px] text-warning">Unsaved changes</span>}
      <Button variant="ghost" size="sm" disabled={!dirty || pending} onClick={onReset}>
        Reset
      </Button>
      <Button size="sm" disabled={!dirty || pending} onClick={onSave}>
        {pending ? "Saving..." : label}
      </Button>
    </>
  );
}

/** A secret the API shows exactly once: copy it now, it cannot be read again. */
export function SecretOnce({ label, value, onDone }: { label: string; value: string; onDone?: () => void }) {
  return (
    <div role="status" className="rounded-xl bg-warning-soft px-4 py-3">
      <div className="flex items-center gap-1.5 text-[12.5px] font-semibold text-warning">
        <KeyRoundIcon className="size-3.5" /> {label}: copy it now, it is shown only once
      </div>
      <div className="mt-2 flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-lg bg-card px-3 py-2 font-mono text-[12.5px] shadow-[var(--elev-1)]">{value}</code>
        <CopyButton value={value} />
      </div>
      {onDone && (
        <Button variant="link" size="xs" className="mt-1.5 text-warning" onClick={onDone}>
          I stored it safely
        </Button>
      )}
    </div>
  );
}

export function AdminOnly() {
  return (
    <Surface>
      <EmptyState
        icon={ShieldIcon}
        title="Admins only"
        description="Settings change how the AI answers and who can do what, so only admins and the owner open them. Ask one of them if something needs changing."
        action={
          <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/inbox" />}>
            Back to the inbox
          </Button>
        }
      />
    </Surface>
  );
}

/** Deep equality for plain JSON values, to know whether a form is dirty. */
export function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** A comma or newline separated list as clean, unique strings. */
export function parseList(text: string): string[] {
  return Array.from(new Set(text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)));
}

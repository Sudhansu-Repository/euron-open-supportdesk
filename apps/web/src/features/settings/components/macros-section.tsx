"use client";

import { PencilIcon, PlusIcon, TextQuoteIcon, Trash2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { useDeleteMacro, useMacros, useSaveMacro } from "@/features/tickets/api";
import { errorMessage } from "@/lib/api/errors";
import type { Macro } from "@/lib/api/types";
import { PLACEHOLDERS } from "@/lib/macros";

import { Card } from "./shared";

function MacroDialog({ macro, open, onOpenChange }: { macro: Macro | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const save = useSaveMacro();
  const [title, setTitle] = React.useState("");
  const [body, setBody] = React.useState("");
  const area = React.useRef<HTMLTextAreaElement>(null);
  React.useEffect(() => {
    if (open) {
      setTitle(macro?.title ?? "");
      setBody(macro?.body ?? "");
    }
  }, [open, macro]);
  function insert(ph: string) {
    const el = area.current;
    if (!el) return setBody((b) => b + ph);
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + ph + body.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + ph.length, start + ph.length);
    });
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{macro ? "Edit canned reply" : "New canned reply"}</DialogTitle>
          <DialogDescription>Agents insert it from the reply box. Placeholders are filled in before sending.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ id: macro?.id, body: { title: title.trim(), body } }, { onSuccess: () => { toast.success("Canned reply saved."); onOpenChange(false); }, onError: (err) => toast.error(errorMessage(err)) });
          }}
        >
          <DialogBody className="space-y-4">
            <Field label="Title" htmlFor="m-title"><Input id="m-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Refund received" /></Field>
            <Field label="Reply" htmlFor="m-body">
              <Textarea id="m-body" ref={area} rows={7} required value={body} onChange={(e) => setBody(e.target.value)} placeholder={"Hi {{customer.first_name}},\n\nThanks for your patience..."} />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {PLACEHOLDERS.map((p) => (
                <button key={p} type="button" onClick={() => insert(p)} className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground hover:text-foreground">{p}</button>
              ))}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={save.isPending || !title.trim() || !body.trim()}>{save.isPending ? "Saving..." : "Save"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MacrosSection() {
  const macros = useMacros();
  const remove = useDeleteMacro();
  const [open, setOpen] = React.useState(false);
  const [edit, setEdit] = React.useState<Macro | null>(null);
  const [del, setDel] = React.useState<Macro | null>(null);
  return (
    <Card title="Canned replies" description="Answers your team gives again and again, one click away in the reply box." action={<Button size="sm" onClick={() => { setEdit(null); setOpen(true); }}><PlusIcon /> New</Button>}>
      {macros.isLoading ? (
        <TableSkeleton rows={3} cols={2} />
      ) : macros.isError ? (
        <ErrorState compact error={macros.error} onRetry={() => void macros.refetch()} />
      ) : !macros.data?.length ? (
        <EmptyState compact icon={TextQuoteIcon} title="No canned replies yet" description="Save the replies you type every day, with placeholders for names. Agents insert them with one click." action={<Button size="sm" variant="outline" onClick={() => { setEdit(null); setOpen(true); }}>Create the first one</Button>} />
      ) : (
        <ul className="space-y-1.5">
          {macros.data.map((m) => (
            <li key={m.id} className="flex items-start gap-3 rounded-xl bg-muted/60 px-3.5 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold">{m.title}</div>
                <p className="mt-0.5 line-clamp-2 text-[12.5px] text-muted-foreground whitespace-pre-wrap">{m.body}</p>
              </div>
              <span className="shrink-0 text-[11.5px] text-subtle tabular">used {m.uses}x</span>
              <Button size="icon-xs" variant="subtle" aria-label={`Edit ${m.title}`} onClick={() => { setEdit(m); setOpen(true); }}><PencilIcon /></Button>
              <Button size="icon-xs" variant="subtle" aria-label={`Delete ${m.title}`} onClick={() => setDel(m)}><Trash2Icon /></Button>
            </li>
          ))}
        </ul>
      )}
      <MacroDialog macro={edit} open={open} onOpenChange={setOpen} />
      <ConfirmDialog
        open={!!del}
        onOpenChange={(o) => !o && setDel(null)}
        title={`Delete "${del?.title ?? ""}"?`}
        description="Agents can no longer insert it. Replies already sent are not affected."
        confirmLabel="Delete"
        pending={remove.isPending}
        onConfirm={() => del && remove.mutate(del.id, { onSuccess: () => { toast.success("Canned reply deleted."); setDel(null); }, onError: (e) => toast.error(errorMessage(e)) })}
      />
    </Card>
  );
}

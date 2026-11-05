"use client";

import { ChevronDownIcon, LockIcon, MessageSquareReplyIcon, SendIcon, SparklesIcon, TextQuoteIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/input";
import { SimpleSelect } from "@/components/ui/select";
import { useMe, useSession } from "@/features/auth/api";
import { useLive } from "@/features/live/agent-live";
import { errorMessage } from "@/lib/api/errors";
import type { Message, TicketDetail, TicketStatus, Tone } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatTokens, formatUsd } from "@/lib/format";
import { methodLabel } from "@/lib/labels";
import { fillPlaceholders } from "@/lib/macros";

import { useApprove, useDraft, useMacros, useReply, useUpdateTicket } from "../api";

const TONES: { value: Tone; label: string }[] = [
  { value: "friendly", label: "Friendly" },
  { value: "formal", label: "Formal" },
  { value: "concise", label: "Concise" },
  { value: "empathetic", label: "Empathetic" },
];

const AFTER: { value: string; label: string }[] = [
  { value: "keep", label: "Keep status" },
  { value: "pending", label: "Then set pending" },
  { value: "resolved", label: "Then resolve" },
];

export interface ReplyBoxHandle {
  focus: () => void;
  loadDraft: (m: Message) => void;
}

/**
 * Reply to the customer or leave an internal note. "Draft with AI" writes a grounded
 * draft from the knowledge base and the transcript, in the chosen tone, for the agent to
 * edit. Canned replies fill their placeholders here, so the agent sees the final text.
 */
export const ReplyBox = React.forwardRef<ReplyBoxHandle, { ticket: TicketDetail }>(function ReplyBox({ ticket }, ref) {
  const [mode, setMode] = React.useState<"reply" | "note">("reply");
  const [body, setBody] = React.useState("");
  const [after, setAfter] = React.useState("keep");
  const [macroId, setMacroId] = React.useState<string | null>(null);
  const [fromDraft, setFromDraft] = React.useState<string | null>(null);
  const [draftInfo, setDraftInfo] = React.useState<string | null>(null);
  const area = React.useRef<HTMLTextAreaElement>(null);
  const reply = useReply(ticket.id);
  const draft = useDraft(ticket.id);
  const approve = useApprove(ticket.id);
  const update = useUpdateTicket(ticket.id);
  const macros = useMacros();
  const { data: me } = useMe();
  const session = useSession();
  const { sendTyping } = useLive();

  React.useImperativeHandle(ref, () => ({
    focus: () => area.current?.focus(),
    loadDraft: (m) => {
      setMode("reply");
      setBody(m.body);
      setFromDraft(m.id);
      setDraftInfo("Loaded the AI draft. Edit it, then send: it goes out as the approved AI answer.");
      requestAnimationFrame(() => area.current?.focus());
    },
  }));

  const closed = ticket.status === "closed";

  function send() {
    const text = body.trim();
    if (!text) return;
    const note = mode === "note";
    if (fromDraft && !note) {
      // An edited AI draft goes out through approval, so the decision trail stays on the draft.
      approve.mutate(
        { messageId: fromDraft, body: text },
        {
          onSuccess: () => {
            setBody("");
            setDraftInfo(null);
            setFromDraft(null);
            if (after !== "keep") update.mutate({ status: after as TicketStatus });
            toast.success("Edited draft sent to the customer.");
          },
          onError: (e) => toast.error(errorMessage(e)),
        },
      );
      return;
    }
    reply.mutate(
      { body: text, note, status: note || after === "keep" ? null : (after as TicketStatus), macro_id: macroId },
      {
        onSuccess: () => {
          setBody("");
          setMacroId(null);
          setDraftInfo(null);
          toast.success(note ? "Note added. Only your team sees it." : after === "resolved" ? "Reply sent and conversation resolved." : "Reply sent.");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  function aiDraft(tone: Tone) {
    draft.mutate(
      { tone },
      {
        onSuccess: (d) => {
          setMode("reply");
          setBody(d.body);
          setDraftInfo(
            d.grounded
              ? `AI draft (${methodLabel(d.method)}, ${d.citations.length} source${d.citations.length === 1 ? "" : "s"}, ${formatTokens(d.tokens)} tokens, ${formatUsd(d.cost_usd)}). Check it before sending.`
              : "The knowledge base does not cover this well, so the draft is a starting point only. Check every fact.",
          );
          requestAnimationFrame(() => area.current?.focus());
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  function insertMacro(id: string) {
    const m = macros.data?.find((x) => x.id === id);
    if (!m) return;
    const text = fillPlaceholders(m.body, {
      customerName: ticket.customer.name,
      customerEmail: ticket.customer.email,
      agentName: me?.name,
      ticketNumber: ticket.number,
      company: session.data?.org_name,
    });
    setBody((b) => (b.trim() ? `${b.trimEnd()}\n\n${text}` : text));
    setMacroId(id);
    requestAnimationFrame(() => area.current?.focus());
  }

  return (
    <div className={cn("rounded-2xl p-3 shadow-[var(--elev-2)] transition-colors", mode === "note" ? "bg-note-soft" : "bg-card")}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Message type" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">
          {(
            [
              { v: "reply", label: "Reply", icon: MessageSquareReplyIcon },
              { v: "note", label: "Internal note", icon: LockIcon },
            ] as const
          ).map((o) => (
            <button
              key={o.v}
              type="button"
              role="radio"
              aria-checked={mode === o.v}
              onClick={() => setMode(o.v)}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium text-muted-foreground transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                mode === o.v && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent",
              )}
            >
              <o.icon className="size-3.5" />
              {o.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="xs" variant="ghost" disabled={draft.isPending || closed} />}>
              <SparklesIcon className="text-ai" />
              {draft.isPending ? "Drafting..." : "Draft with AI"}
              <ChevronDownIcon className="size-3 opacity-60" />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-52">
              <DropdownMenuLabel>Tone of the draft</DropdownMenuLabel>
              {TONES.map((t) => (
                <DropdownMenuItem key={t.value} onClick={() => aiDraft(t.value)}>
                  {t.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="xs" variant="ghost" disabled={closed} />}>
              <TextQuoteIcon />
              Canned
              <ChevronDownIcon className="size-3 opacity-60" />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-72">
              <DropdownMenuLabel>Canned replies</DropdownMenuLabel>
              {macros.isLoading && <DropdownMenuLabel>Loading...</DropdownMenuLabel>}
              {macros.isError && <DropdownMenuLabel className="text-danger">Could not load canned replies.</DropdownMenuLabel>}
              {macros.data?.length === 0 && (
                <DropdownMenuLabel className="leading-relaxed">
                  No canned replies yet. An admin adds them in Settings, with placeholders like {"{{customer.first_name}}"}.
                </DropdownMenuLabel>
              )}
              {macros.data?.map((m) => (
                <DropdownMenuItem key={m.id} onClick={() => insertMacro(m.id)} className="flex-col items-start gap-0.5">
                  <span className="font-medium">{m.title}</span>
                  <span className="line-clamp-1 text-xs text-muted-foreground">{m.body}</span>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem render={<Link href="/settings/macros" />}>Manage canned replies</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <Textarea
        ref={area}
        value={body}
        disabled={closed}
        onChange={(e) => {
          setBody(e.target.value);
          if (mode === "reply") sendTyping(ticket.id);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            send();
          }
        }}
        rows={4}
        aria-label={mode === "note" ? "Internal note" : `Reply to ${ticket.customer.name}`}
        placeholder={
          closed
            ? "This conversation is closed. Reopen it from the status menu to reply."
            : mode === "note"
              ? "Write a note for your team. The customer never sees it."
              : `Reply to ${ticket.customer.name}...`
        }
        className={cn("min-h-24 resize-y border-0 text-[13.5px] shadow-none ring-0 focus-visible:ring-0", mode === "note" ? "bg-transparent dark:bg-transparent" : "bg-transparent dark:bg-transparent")}
      />
      {draftInfo && <p className="mt-1.5 px-1 text-[11.5px] text-ai">{draftInfo}</p>}
      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto hidden px-1 text-[11px] text-faint sm:inline">Ctrl or Cmd + Enter to send</span>
        {mode === "reply" && <SimpleSelect size="sm" aria-label="Status after sending" className="w-[150px]" value={after} onValueChange={setAfter} options={AFTER} />}
        <Button size="sm" onClick={send} disabled={!body.trim() || reply.isPending || approve.isPending || closed}>
          {mode === "note" ? <LockIcon /> : <SendIcon />}
          {reply.isPending ? "Sending..." : mode === "note" ? "Add note" : "Send reply"}
        </Button>
      </div>
    </div>
  );
});

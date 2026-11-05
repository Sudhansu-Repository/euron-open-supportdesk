"use client";

import { AtSignIcon, CodeIcon, GlobeIcon, MessageCircleIcon, PlusIcon, RefreshCwIcon, ShieldCheckIcon, XIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/features/auth/api";
import { WidgetChat } from "@/features/widget/components/widget-chat";
import { readableOn, safeColor } from "@/features/widget/state";
import { errorMessage } from "@/lib/api/errors";
import type { Inbox, PublicMessage } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { channelLabel } from "@/lib/labels";
import { obj, str, strs } from "@/lib/read";

import { useInboxes, useUpdateInbox } from "../api";

import { Card, SaveFooter, sameJson, SecretOnce } from "./shared";

const ICON: Record<string, React.ComponentType<{ className?: string }>> = { widget: MessageCircleIcon, email: AtSignIcon, portal: GlobeIcon, api: CodeIcon };

interface Appearance {
  title: string;
  greeting: string;
  color: string;
  position: "left" | "right";
  launcher_label: string;
  suggestions: string[];
}

export function readAppearance(raw: unknown): Appearance {
  const a = obj(raw);
  return {
    title: str(a.title) ?? "Support",
    greeting: str(a.greeting) ?? "Hi! Ask us anything.",
    color: safeColor(str(a.color)),
    position: str(a.position) === "left" ? "left" : "right",
    launcher_label: str(a.launcher_label) ?? "Help",
    suggestions: strs(a.suggestions),
  };
}

/** Normalise an origin the way the API does: scheme, lowercase host, optional port. */
export function normalizeOrigin(input: string): string | null {
  try {
    const u = new URL(input.trim());
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    return `${u.protocol}//${u.hostname.toLowerCase()}${u.port ? `:${u.port}` : ""}`;
  } catch {
    return null;
  }
}

const DEMO: PublicMessage[] = [
  { id: "d1", author_type: "customer", body: "How do I change my plan?", citations: [], feedback: null, created_at: "2026-01-01T10:00:00Z" },
  {
    id: "d2",
    author_type: "ai",
    body: "Open **Billing**, choose **Change plan**, and pick the new one. The difference is prorated on your next invoice.",
    citations: [{ title: "Billing guide", heading: "Changing your plan", url: null }],
    feedback: null,
    created_at: "2026-01-01T10:00:02Z",
  },
];

function WidgetPreview({ a, company }: { a: Appearance; company: string }) {
  const accent = safeColor(a.color);
  const text = readableOn(accent);
  const [mode, setMode] = React.useState<"empty" | "chat">("empty");
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold tracking-[0.06em] text-subtle uppercase">Live preview</span>
        <Segmented ariaLabel="Preview state" className="w-56 whitespace-nowrap" value={mode} onChange={setMode} options={[{ value: "empty", label: "First open" }, { value: "chat", label: "Answer" }]} />
      </div>
      <div className="relative rounded-2xl bg-muted/70 p-4 pb-20">
        <div className="mx-auto h-[540px] w-full max-w-[360px] overflow-hidden rounded-[18px] shadow-[var(--elev-4)]" aria-label="Widget preview">
          <WidgetChat
            preview
            title={a.title || "Support"}
            greeting={a.greeting}
            company={company}
            accent={accent}
            accentText={text}
            suggestions={a.suggestions}
            agentsOnline
            aiEnabled
            messages={mode === "chat" ? DEMO : []}
            typing={false}
            sending={false}
            votes={{}}
            canAskHuman={mode === "chat"}
            showEmail={false}
            emailSent={false}
            showRating={false}
            rated={false}
            onSend={() => setMode("chat")}
            onVote={() => undefined}
            onHuman={() => undefined}
            onEmail={() => undefined}
            onRate={() => undefined}
            onClose={() => undefined}
          />
        </div>
        <div className={cn("absolute bottom-4 flex h-12 items-center gap-2 rounded-full px-4 text-[13px] font-semibold shadow-[var(--elev-3)]", a.position === "left" ? "left-4" : "right-4")} style={{ background: accent, color: text }} aria-hidden>
          <MessageCircleIcon className="size-4" /> {a.launcher_label || "Help"}
        </div>
      </div>
    </div>
  );
}

function OriginList({ origins, onChange }: { origins: string[]; onChange: (o: string[]) => void }) {
  const [value, setValue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  function add() {
    const o = normalizeOrigin(value);
    if (!o) return setError("Use a full origin like https://www.example.com (no path).");
    setError(null);
    if (!origins.includes(o)) onChange([...origins, o]);
    setValue("");
  }
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="https://www.example.com"
          aria-label="Add an allowed site"
          aria-invalid={!!error || undefined}
        />
        <Button type="button" variant="outline" onClick={add} disabled={!value.trim()}>
          <PlusIcon /> Add
        </Button>
      </div>
      {error && <p className="text-[12px] text-danger">{error}</p>}
      {origins.length === 0 ? (
        <p className="rounded-lg bg-warning-soft px-3 py-2 text-[12px] text-warning">No site listed: any website can embed this widget. Fine for trying it out; list your sites before going live.</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {origins.map((o) => (
            <li key={o} className="inline-flex h-7 items-center gap-1 rounded-full bg-muted pr-1 pl-3 font-mono text-[12px]">
              {o}
              <button type="button" aria-label={`Remove ${o}`} onClick={() => onChange(origins.filter((x) => x !== o))} className="rounded-full p-1 text-subtle hover:text-foreground">
                <XIcon className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface WidgetForm {
  name: string;
  appearance: Appearance;
  allowed_origins: string[];
  identity_required: boolean;
  ai_enabled: boolean;
  active: boolean;
}

function WidgetDesigner({ inbox }: { inbox: Inbox }) {
  const update = useUpdateInbox();
  const session = useSession();
  const initial = React.useMemo<WidgetForm>(
    () => ({
      name: inbox.name,
      appearance: readAppearance(inbox.appearance),
      allowed_origins: inbox.allowed_origins,
      identity_required: inbox.identity_required,
      ai_enabled: inbox.ai_enabled,
      active: inbox.active,
    }),
    [inbox],
  );
  const [f, setF] = React.useState(initial);
  const [suggestions, setSuggestions] = React.useState(initial.appearance.suggestions.join("\n"));
  const [secret, setSecret] = React.useState<string | null>(null);
  React.useEffect(() => {
    setF(initial);
    setSuggestions(initial.appearance.suggestions.join("\n"));
  }, [initial]);

  const live: Appearance = { ...f.appearance, suggestions: suggestions.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 6) };
  const next = { ...f, appearance: live };
  const dirty = !sameJson(next, initial);
  const setA = (patch: Partial<Appearance>) => setF({ ...f, appearance: { ...f.appearance, ...patch } });
  const company = session.data?.org_name ?? "Your company";
  const snippet = inbox.snippet ?? `<script src="${typeof window !== "undefined" ? window.location.origin : ""}/widget.js" data-key="${inbox.public_key ?? ""}" async></script>`;
  const scriptSrc = /src="([^"]+)"/.exec(snippet)?.[1] ?? "/widget.js";
  const identitySnippet = `<script src="${scriptSrc}" data-key="${inbox.public_key ?? ""}"\n  data-external-id="{{ user.id }}" data-signature="{{ hmac_sha256(identity_secret, user.id) }}"\n  data-email="{{ user.email }}" data-name="{{ user.name }}" async></script>`;

  function save() {
    update.mutate(
      { id: inbox.id, body: { name: next.name, appearance: { ...live }, allowed_origins: next.allowed_origins, identity_required: next.identity_required, ai_enabled: next.ai_enabled, active: next.active } },
      { onSuccess: () => toast.success("Widget saved. Open pages pick it up on the next load."), onError: (e) => toast.error(errorMessage(e)) },
    );
  }

  function rotate() {
    update.mutate(
      { id: inbox.id, body: { rotate_identity_secret: true } },
      {
        onSuccess: (saved) => {
          if (saved.secret) setSecret(saved.secret);
          toast.success("New identity secret created. Update your backend before turning verification on.");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <div className="space-y-5">
      <Card title="Install" description="Paste this before </body> on every page where customers should see the chat. That is the whole installation.">
        <div className="overflow-hidden rounded-xl bg-code-bg">
          <div className="flex items-center justify-between gap-2 px-4 pt-2.5">
            <span className="text-[11px] font-semibold tracking-[0.06em] text-code-fg/60 uppercase">HTML</span>
            <CopyButton value={snippet} label="Copy snippet" variant="default" />
          </div>
          <pre className="px-4 pt-2 pb-3.5 font-mono text-[12.5px] leading-relaxed break-all whitespace-pre-wrap text-code-fg">{snippet}</pre>
        </div>
        <p className="mt-2 text-[12px] text-muted-foreground">
          Call <code className="rounded bg-muted px-1 font-mono">SupportDesk.open()</code> from your own button to open it. The widget only loads on the sites you allow below.
        </p>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        <Card title="Design" description="Changes show in the preview as you type." footer={<SaveFooter dirty={dirty} pending={update.isPending} onReset={() => { setF(initial); setSuggestions(initial.appearance.suggestions.join("\n")); }} onSave={save} />}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Title" htmlFor="w-title">
              <Input id="w-title" value={f.appearance.title} onChange={(e) => setA({ title: e.target.value })} maxLength={60} />
            </Field>
            <Field label="Launcher label" htmlFor="w-label">
              <Input id="w-label" value={f.appearance.launcher_label} onChange={(e) => setA({ launcher_label: e.target.value })} maxLength={24} />
            </Field>
            <Field label="Colour" htmlFor="w-color">
              <div className="flex items-center gap-2">
                <input type="color" aria-label="Pick the widget colour" value={f.appearance.color} onChange={(e) => setA({ color: e.target.value })} className="h-9 w-12 cursor-pointer rounded-lg bg-transparent" />
                <Input id="w-color" value={f.appearance.color} onChange={(e) => setA({ color: e.target.value })} className="font-mono" />
              </div>
            </Field>
            <Field label="Position" htmlFor="w-pos">
              <Segmented ariaLabel="Position" value={f.appearance.position} onChange={(v) => setA({ position: v })} options={[{ value: "left", label: "Bottom left" }, { value: "right", label: "Bottom right" }]} />
            </Field>
          </div>
          <Field className="mt-4" label="Greeting" htmlFor="w-greet" hint="The first thing visitors read.">
            <Textarea id="w-greet" rows={2} value={f.appearance.greeting} onChange={(e) => setA({ greeting: e.target.value })} maxLength={400} />
          </Field>
          <Field className="mt-4" label="Suggested questions" htmlFor="w-sugg" hint="One per line, up to 6. Shown as chips before the first message.">
            <Textarea id="w-sugg" rows={3} value={suggestions} onChange={(e) => setSuggestions(e.target.value)} placeholder={"How do I reset my password?\nWhat does it cost?"} />
          </Field>
          <div className="mt-5 space-y-2">
            <div className="flex items-center gap-1.5 text-[13px] font-medium">Allowed sites</div>
            <p className="text-[12px] text-muted-foreground">Only these sites may embed the chat (enforced by the browser with a Content-Security-Policy). Changes apply within a minute.</p>
            <OriginList origins={f.allowed_origins} onChange={(o) => setF({ ...f, allowed_origins: o })} />
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
              <span>
                <span className="font-medium">AI answers</span>
                <span className="block text-[12px] text-muted-foreground">Off: every chat goes to your team.</span>
              </span>
              <Switch checked={f.ai_enabled} onCheckedChange={(v) => setF({ ...f, ai_enabled: v })} />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
              <span>
                <span className="font-medium">Widget active</span>
                <span className="block text-[12px] text-muted-foreground">Off: the chat shows as unavailable.</span>
              </span>
              <Switch checked={f.active} onCheckedChange={(v) => setF({ ...f, active: v })} />
            </label>
          </div>
        </Card>
        <div className="xl:sticky xl:top-20 xl:self-start">
          <WidgetPreview a={live} company={company} />
        </div>
      </div>

      <Card
        title={
          <>
            Identity verification <Hint term="identityVerification" />
          </>
        }
        description="For signed-in customers: your backend signs their id with HMAC-SHA256 and this secret, and the widget refuses unsigned or forged identities."
        action={inbox.identity_secret_set ? <Chip tone="success">Secret set</Chip> : <Chip tone="neutral">No secret yet</Chip>}
      >
        <div className="space-y-3">
          <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
            <span>
              <span className="flex items-center gap-1.5 font-medium">
                <ShieldCheckIcon className="size-4 text-primary" /> Require verified identities
              </span>
              <span className="block text-[12px] text-muted-foreground">Turn on after your backend sends the signature, or signed-in visitors are refused.</span>
            </span>
            <Switch checked={f.identity_required} disabled={!inbox.identity_secret_set} onCheckedChange={(v) => setF({ ...f, identity_required: v })} />
          </label>
          <Button variant="outline" size="sm" onClick={rotate} disabled={update.isPending}>
            <RefreshCwIcon /> {inbox.identity_secret_set ? "Rotate the secret" : "Create a secret"}
          </Button>
          {secret && <SecretOnce label="Identity secret" value={secret} onDone={() => setSecret(null)} />}
          {(inbox.identity_secret_set || secret) && (
            <div className="space-y-2 pt-1">
              <div className="text-[13px] font-medium">Snippet for signed-in pages</div>
              <p className="text-[12px] text-muted-foreground">
                Your backend renders the user id and <code className="rounded bg-muted px-1 font-mono">HMAC-SHA256(secret, user id)</code> as a hex string. Never compute the hash in the browser.
              </p>
              <div className="overflow-hidden rounded-xl bg-code-bg">
                <div className="flex items-center justify-between gap-2 px-4 pt-2.5">
                  <span className="text-[11px] font-semibold tracking-[0.06em] text-code-fg/60 uppercase">HTML</span>
                  <CopyButton value={identitySnippet} label="Copy snippet" variant="default" />
                </div>
                <pre className="px-4 pt-2 pb-3.5 font-mono text-[12.5px] leading-relaxed break-all whitespace-pre-wrap text-code-fg">{identitySnippet}</pre>
              </div>
              <p className="text-[12px] text-muted-foreground">
                In a single-page app, call <code className="rounded bg-muted px-1 font-mono">SupportDesk.identify({"{ externalId, signature, email, name }"})</code> after sign-in, and{" "}
                <code className="rounded bg-muted px-1 font-mono">SupportDesk.logout()</code> after sign-out.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function EmailInbox({ inbox }: { inbox: Inbox }) {
  const update = useUpdateInbox();
  const [address, setAddress] = React.useState(inbox.email_address ?? "");
  const [secret, setSecret] = React.useState<string | null>(null);
  React.useEffect(() => setAddress(inbox.email_address ?? ""), [inbox.email_address]);
  const url = secret && inbox.inbound_url ? inbox.inbound_url.replace("<token>", secret) : inbox.inbound_url;
  return (
    <div className="space-y-5">
      <Card
        title="Email address"
        description="Customers write here; replies leave from it with threading headers, so their answer lands in the same conversation."
        footer={
          <SaveFooter
            dirty={address.trim() !== (inbox.email_address ?? "")}
            pending={update.isPending}
            onReset={() => setAddress(inbox.email_address ?? "")}
            onSave={() => update.mutate({ id: inbox.id, body: { email_address: address.trim() || null } }, { onSuccess: () => toast.success("Email address saved."), onError: (e) => toast.error(errorMessage(e)) })}
          />
        }
      >
        <Field label="Support address" htmlFor="e-addr">
          <Input id="e-addr" type="email" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="support@example.com" />
        </Field>
      </Card>
      <Card
        title="Inbound email"
        description="Forward incoming mail (raw RFC 822, or SES through SNS) to this URL. The token in it is the password: keep it private."
        action={inbox.inbound_configured ? <Chip tone="success">Configured</Chip> : <Chip tone="warning">No token yet</Chip>}
      >
        <div className="space-y-3">
          {url && (
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg bg-muted px-3 py-2 font-mono text-[12px]">{url}</code>
              {secret && <CopyButton value={url} />}
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={update.isPending}
            onClick={() =>
              update.mutate(
                { id: inbox.id, body: { rotate_inbound_token: true } },
                { onSuccess: (s) => { if (s.secret) setSecret(s.secret); toast.success("New inbound token. Update your mail forwarding."); }, onError: (e) => toast.error(errorMessage(e)) },
              )
            }
          >
            <RefreshCwIcon /> {inbox.inbound_configured ? "Rotate the inbound token" : "Create an inbound token"}
          </Button>
          {secret && <SecretOnce label="Inbound token" value={secret} onDone={() => setSecret(null)} />}
        </div>
      </Card>
    </div>
  );
}

function SimpleInbox({ inbox }: { inbox: Inbox }) {
  const update = useUpdateInbox();
  return (
    <Card title={inbox.name} description={inbox.channel === "portal" ? "Customers sign in to your help center with a magic link and open or follow tickets." : "Tickets created through the REST API with an API key."}>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
          <span className="font-medium">AI answers</span>
          <Switch checked={inbox.ai_enabled} onCheckedChange={(v) => update.mutate({ id: inbox.id, body: { ai_enabled: v } }, { onSuccess: () => toast.success(v ? "AI answers on." : "AI answers off."), onError: (e) => toast.error(errorMessage(e)) })} />
        </label>
        <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
          <span className="font-medium">Active</span>
          <Switch checked={inbox.active} onCheckedChange={(v) => update.mutate({ id: inbox.id, body: { active: v } }, { onSuccess: () => toast.success(v ? "Inbox active." : "Inbox paused."), onError: (e) => toast.error(errorMessage(e)) })} />
        </label>
      </div>
    </Card>
  );
}

export function InboxesSection() {
  const inboxes = useInboxes();
  const [selected, setSelected] = React.useState<string | null>(null);
  if (inboxes.isLoading) return <Skeleton className="h-96 rounded-2xl" />;
  if (inboxes.isError || !inboxes.data) return <ErrorState error={inboxes.error} title="Could not load inboxes" onRetry={() => void inboxes.refetch()} />;
  const list = inboxes.data;
  const current = list.find((i) => i.id === selected) ?? list.find((i) => i.channel === "widget") ?? list[0];
  return (
    <div className="space-y-5">
      <div role="tablist" aria-label="Inboxes" className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
        {list.map((i) => {
          const Icon = ICON[i.channel] ?? MessageCircleIcon;
          const active = current?.id === i.id;
          return (
            <button
              key={i.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setSelected(i.id)}
              className={cn("flex shrink-0 items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-ring", active ? "bg-card shadow-[var(--elev-2)]" : "bg-muted/60 hover:bg-muted")}
            >
              <Icon className={cn("size-4", active ? "text-primary" : "text-subtle")} />
              <span>
                <span className="block text-[13px] font-semibold">{i.name}</span>
                <span className="block text-[11.5px] text-muted-foreground">
                  {channelLabel(i.channel)}
                  {!i.active && " (paused)"}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {current ? current.channel === "widget" ? <WidgetDesigner key={current.id} inbox={current} /> : current.channel === "email" ? <EmailInbox key={current.id} inbox={current} /> : <SimpleInbox key={current.id} inbox={current} /> : null}
    </div>
  );
}

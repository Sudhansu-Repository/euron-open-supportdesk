"use client";

import { CheckCircle2Icon, CpuIcon, KeyRoundIcon, Loader2Icon, PlugZapIcon, ServerIcon, XCircleIcon, ZapIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { AiConfig, AiProvider } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMs } from "@/lib/format";

import { useSettings, useTestAi, useUpdateSettings } from "../api";

import { Card, SaveFooter, sameJson } from "./shared";

export const PROVIDERS: { value: AiProvider; label: string; body: string; icon: React.ComponentType<{ className?: string }>; needsKey: boolean; needsUrl: boolean; example: { base: string; answer: string; triage: string } }[] = [
  { value: "extractive", label: "Extractive", body: "Zero API key. Quotes the best passage of your docs with its source. No model, no tokens, nothing leaves the server.", icon: ZapIcon, needsKey: false, needsUrl: false, example: { base: "", answer: "", triage: "" } },
  { value: "ollama", label: "Ollama", body: "A local model on your own machine or GPU box. Private, no per-token cost.", icon: ServerIcon, needsKey: false, needsUrl: true, example: { base: "http://ollama:11434", answer: "llama3.1:8b", triage: "llama3.2:3b" } },
  { value: "openai", label: "OpenAI-compatible", body: "OpenAI, vLLM, a LiteLLM proxy, TokenShield or any server speaking the OpenAI API.", icon: PlugZapIcon, needsKey: true, needsUrl: true, example: { base: "https://api.openai.com/v1", answer: "gpt-4o-mini", triage: "gpt-4o-mini" } },
  { value: "anthropic", label: "Anthropic", body: "Claude models through the Anthropic API.", icon: CpuIcon, needsKey: true, needsUrl: false, example: { base: "https://api.anthropic.com", answer: "claude-sonnet-4-5", triage: "claude-haiku-4-5" } },
];

export function AiSection() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const test = useTestAi();
  const initial = React.useMemo<AiConfig | null>(() => (settings.data ? { ...settings.data.ai } : null), [settings.data]);
  const [ai, setAi] = React.useState<AiConfig | null>(initial);
  const [key, setKey] = React.useState("");
  React.useEffect(() => setAi(initial), [initial]);

  if (settings.isLoading || !ai || !initial) return settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : <Skeleton className="h-96 rounded-2xl" />;
  const provider = PROVIDERS.find((p) => p.value === (ai.provider ?? "extractive")) ?? PROVIDERS[0]!;
  const dirty = !sameJson(ai, initial) || key.length > 0;
  const set = (patch: Partial<AiConfig>) => setAi({ ...ai, ...patch });

  function save() {
    update.mutate(
      { ai: { ...ai, base_url: ai?.base_url || null, answer_model: ai?.answer_model || null, triage_model: ai?.triage_model || null }, ...(key ? { ai_api_key: key } : {}) },
      {
        onSuccess: () => {
          setKey("");
          toast.success("AI settings saved. Run the connection test to be sure.");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <div className="space-y-5">
      <Card title="Who writes the answers" description="Every provider answers only from your knowledge, and the policy decides what is sent. Switch any time.">
        <div role="radiogroup" aria-label="AI provider" className="grid gap-2 sm:grid-cols-2">
          {PROVIDERS.map((p) => {
            const active = provider.value === p.value;
            return (
              <button
                key={p.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => set({ provider: p.value, base_url: p.needsUrl ? ai.base_url || p.example.base : null })}
                className={cn("flex gap-3 rounded-xl px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-ring", active ? "bg-primary-soft ring-2 ring-primary/50" : "bg-muted/60 hover:bg-muted")}
              >
                <p.icon className={cn("mt-0.5 size-4 shrink-0", active ? "text-primary" : "text-subtle")} />
                <span>
                  <span className="flex items-center gap-2 text-[13.5px] font-semibold">
                    {p.label}
                    {p.value === "extractive" && <Chip tone="success">Zero API key</Chip>}
                  </span>
                  <span className="mt-0.5 block text-[12.5px] leading-relaxed text-muted-foreground">{p.body}</span>
                </span>
              </button>
            );
          })}
        </div>
      </Card>

      <Card
        title="Connection and models"
        description={provider.value === "extractive" ? "Nothing to configure: answers are passages of your own documents." : "Where the model runs and which models to use. A cheaper triage model keeps costs down."}
        footer={<SaveFooter dirty={dirty} pending={update.isPending} onReset={() => { setAi(initial); setKey(""); }} onSave={save} />}
        action={
          <Button
            size="sm"
            variant="outline"
            disabled={test.isPending || dirty}
            title={dirty ? "Save first, then test" : undefined}
            onClick={() => test.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) })}
          >
            {test.isPending ? <Loader2Icon className="animate-spin" /> : <PlugZapIcon />} Test connection
          </Button>
        }
      >
        {test.data && (
          <div role="status" className={cn("mb-4 flex gap-2.5 rounded-xl px-4 py-3 text-[13px]", test.data.ok ? "bg-savings-soft" : "bg-danger-soft")}>
            {test.data.ok ? <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-savings" /> : <XCircleIcon className="mt-0.5 size-4 shrink-0 text-danger" />}
            <div className="min-w-0">
              <div className={cn("font-semibold", test.data.ok ? "text-savings" : "text-danger")}>
                {test.data.ok ? "Connected" : "Could not connect"}: {test.data.provider}
                {test.data.model ? ` / ${test.data.model}` : ""} in {formatMs(test.data.latency_ms)}
              </div>
              <div className="mt-0.5 text-muted-foreground">{test.data.message}</div>
              {test.data.sample && <div className="mt-1 truncate text-[12px] text-subtle">Sample: {test.data.sample}</div>}
            </div>
          </div>
        )}
        {provider.value !== "extractive" && (
          <div className="grid gap-4 sm:grid-cols-2">
            {provider.needsUrl && (
              <Field label="Base URL" htmlFor="ai-url" className="sm:col-span-2" hint={provider.value === "ollama" ? "The Ollama server, as the API container reaches it." : "Ends with /v1 for most OpenAI-compatible servers."}>
                <Input id="ai-url" value={ai.base_url ?? ""} onChange={(e) => set({ base_url: e.target.value })} placeholder={provider.example.base} />
              </Field>
            )}
            <Field label="Answer model" htmlFor="ai-answer" hint="Writes the answers customers read.">
              <Input id="ai-answer" value={ai.answer_model ?? ""} onChange={(e) => set({ answer_model: e.target.value })} placeholder={provider.example.answer} />
            </Field>
            <Field label="Triage model" htmlFor="ai-triage" hint="Reads intent and sentiment. A small model is plenty.">
              <Input id="ai-triage" value={ai.triage_model ?? ""} onChange={(e) => set({ triage_model: e.target.value })} placeholder={provider.example.triage} />
            </Field>
            {provider.needsKey && (
              <Field
                label="API key"
                htmlFor="ai-key"
                className="sm:col-span-2"
                labelExtra={settings.data?.ai_key_set ? <Chip tone="success">Stored</Chip> : <Chip tone="warning">Not set</Chip>}
                hint="Write-only: it is sealed on the server and never shown again. Leave empty to keep the stored key."
              >
                <div className="relative">
                  <KeyRoundIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
                  <Input id="ai-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={settings.data?.ai_key_set ? "A key is stored. Type to replace it." : "Paste the provider key"} className="pl-9" />
                </div>
              </Field>
            )}
            <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px] sm:col-span-2">
              <span>
                <span className="font-medium">Use the model for triage</span>
                <span className="block text-[12px] text-muted-foreground">Off: fast keyword rules read intent and sentiment. On: the triage model can only make the outcome more careful.</span>
              </span>
              <Switch checked={!!ai.llm_triage} onCheckedChange={(v) => set({ llm_triage: v })} />
            </label>
          </div>
        )}
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Field label="Embedder" htmlFor="ai-embed" labelExtra={<Hint term="embedder" />} hint="Local runs on the CPU with no key.">
            <SimpleSelect
              id="ai-embed"
              value={ai.embedder ?? "local"}
              onValueChange={(v) => set({ embedder: v as AiConfig["embedder"] })}
              options={[
                { value: "local", label: "Local (ONNX, no key)" },
                { value: "ollama", label: "Ollama" },
                { value: "openai", label: "OpenAI-compatible" },
              ]}
            />
          </Field>
          <Field label="Passages per answer" htmlFor="ai-topk" hint="How many top passages the model reads.">
            <Input id="ai-topk" type="number" min={1} max={20} value={ai.top_k ?? 5} onChange={(e) => set({ top_k: Number(e.target.value) })} />
          </Field>
          <Field label="Max answer tokens" htmlFor="ai-max" hint="Caps the length and the cost of each answer.">
            <Input id="ai-max" type="number" min={64} max={4000} value={ai.max_answer_tokens ?? 400} onChange={(e) => set({ max_answer_tokens: Number(e.target.value) })} />
          </Field>
          {ai.embedder && ai.embedder !== "local" && (
            <>
              <Field label="Embedding base URL" htmlFor="ai-eurl">
                <Input id="ai-eurl" value={ai.embed_base_url ?? ""} onChange={(e) => set({ embed_base_url: e.target.value || null })} />
              </Field>
              <Field label="Embedding model" htmlFor="ai-emodel">
                <Input id="ai-emodel" value={ai.embed_model ?? ""} onChange={(e) => set({ embed_model: e.target.value || null })} />
              </Field>
              <Field label="Dimensions" htmlFor="ai-edims" hint="384, 768, 1024 or 1536.">
                <Input id="ai-edims" type="number" value={ai.embed_dims ?? ""} onChange={(e) => set({ embed_dims: e.target.value ? Number(e.target.value) : null })} />
              </Field>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}

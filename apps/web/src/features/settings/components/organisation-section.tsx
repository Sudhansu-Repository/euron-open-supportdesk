"use client";

import { ExternalLinkIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { ThemeSelector } from "@/components/theme-toggle";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import type { Brand } from "@/lib/api/types";

import { useSettings, useUpdateSettings } from "../api";

import { Card, parseList, SaveFooter, sameJson } from "./shared";

interface Form {
  name: string;
  brand: Brand;
  categories: string;
}

const HEX = /^#[0-9a-f]{6}$/i;

export function OrganisationSection() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const initial = React.useMemo<Form | null>(
    () => (settings.data ? { name: settings.data.org.name, brand: { ...settings.data.brand }, categories: settings.data.categories.join(", ") } : null),
    [settings.data],
  );
  const [form, setForm] = React.useState<Form | null>(initial);
  React.useEffect(() => setForm(initial), [initial]);

  if (settings.isLoading || !form || !initial) return settings.isError ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : <Skeleton className="h-96 rounded-2xl" />;
  const dirty = !sameJson(form, initial);
  const accent = form.brand.accent_color ?? "#4f46e5";
  const slug = settings.data?.org.slug;
  const set = (b: Partial<Brand>) => setForm({ ...form, brand: { ...form.brand, ...b } });

  function save() {
    if (!form) return;
    if (form.brand.accent_color && !HEX.test(form.brand.accent_color)) return toast.error("Use a colour like #4f46e5.");
    update.mutate(
      { name: form.name.trim(), brand: { ...form.brand, support_email: form.brand.support_email || null, website: form.brand.website || null }, categories: parseList(form.categories) },
      { onSuccess: () => toast.success("Organisation saved."), onError: (e) => toast.error(errorMessage(e)) },
    );
  }

  return (
    <div className="space-y-5">
      <Card
        title="Organisation and brand"
        description="Shown to customers in the widget, emails and the help center."
        footer={<SaveFooter dirty={dirty} pending={update.isPending} onReset={() => setForm(initial)} onSave={save} />}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Organisation name" htmlFor="o-name">
            <Input id="o-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Company name customers see" htmlFor="o-company">
            <Input id="o-company" value={form.brand.company_name ?? ""} onChange={(e) => set({ company_name: e.target.value })} />
          </Field>
          <Field label="Support email" htmlFor="o-email" hint="Replies to email conversations come from here.">
            <Input id="o-email" type="email" value={form.brand.support_email ?? ""} onChange={(e) => set({ support_email: e.target.value })} placeholder="support@example.com" />
          </Field>
          <Field label="Website" htmlFor="o-web">
            <Input id="o-web" type="url" value={form.brand.website ?? ""} onChange={(e) => set({ website: e.target.value })} placeholder="https://www.example.com" />
          </Field>
          <Field label="Help center title" htmlFor="o-hc">
            <Input id="o-hc" value={form.brand.help_center_title ?? ""} onChange={(e) => set({ help_center_title: e.target.value })} />
          </Field>
          <Field label="Accent colour" htmlFor="o-accent" hint="Used by the help center and the portal.">
            <div className="flex items-center gap-2">
              <input type="color" aria-label="Pick the accent colour" value={HEX.test(accent) ? accent : "#4f46e5"} onChange={(e) => set({ accent_color: e.target.value })} className="h-9 w-12 cursor-pointer rounded-lg bg-transparent" />
              <Input id="o-accent" value={accent} onChange={(e) => set({ accent_color: e.target.value })} className="font-mono" />
            </div>
          </Field>
        </div>
        <Field className="mt-4" label="Categories" htmlFor="o-cats" hint="Comma separated. Triage files each conversation under one of these, and Policy decides which ones the AI may resolve.">
          <Textarea id="o-cats" rows={2} value={form.categories} onChange={(e) => setForm({ ...form, categories: e.target.value })} />
        </Field>
        {slug && (
          <a href={`/help/${slug}`} target="_blank" rel="noopener" className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline">
            Open your public help center at /help/{slug} <ExternalLinkIcon className="size-3.5" />
          </a>
        )}
      </Card>
      <Card title="Appearance" description="Your own theme for this browser. Customers see the widget in your accent colour.">
        <ThemeSelector />
      </Card>
    </div>
  );
}

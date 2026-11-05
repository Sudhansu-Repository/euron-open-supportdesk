"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";

import { useCreatePortalTicket } from "../api";

import { usePortalGuard } from "./portal-tickets";

export function PortalNewTicket({ slug }: { slug: string }) {
  const { token } = usePortalGuard(slug);
  const create = useCreatePortalTicket(slug, token);
  const router = useRouter();
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  return (
    <div className="mx-auto max-w-2xl">
      <Link href={`/help/${slug}/tickets`} className="inline-flex items-center gap-1 text-[13px] font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" /> My tickets
      </Link>
      <form
        className="surface mt-4 space-y-4 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (!subject.trim() || !body.trim()) return setError("Add a short subject and describe what you need.");
          setError(null);
          create.mutate({ subject: subject.trim(), body: body.trim() }, { onSuccess: (t) => router.replace(`/help/${slug}/tickets/${t.id}`), onError: (err) => setError(errorMessage(err)) });
        }}
      >
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em]">New ticket</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">Our assistant answers right away when it can; otherwise a teammate replies here and by email.</p>
        </div>
        <Field label="Subject" htmlFor="t-subject">
          <Input id="t-subject" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} placeholder="I cannot download my invoice" />
        </Field>
        <Field label="Details" htmlFor="t-body" hint="Steps, error messages, order numbers: anything that helps us help you.">
          <Textarea id="t-body" rows={7} value={body} onChange={(e) => setBody(e.target.value)} maxLength={10000} />
        </Field>
        {error && <FieldError>{error}</FieldError>}
        <Button type="submit" disabled={create.isPending || !token}>{create.isPending ? "Sending..." : "Send"}</Button>
      </form>
    </div>
  );
}

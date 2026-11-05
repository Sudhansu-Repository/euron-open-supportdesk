"use client";

import { Loader2Icon, MailCheckIcon, MailIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FieldError, Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";

import { usePortalToken, useRedeemLink, useRequestLink } from "../api";

/** Magic-link sign-in: email in, link out; the link comes back here with ?token=. */
export function PortalSignin({ slug }: { slug: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const linkToken = params.get("token");
  const { set } = usePortalToken(slug);
  const request = useRequestLink(slug);
  const redeem = useRedeemLink(slug);
  const [email, setEmail] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const redeemed = React.useRef(false);

  React.useEffect(() => {
    if (!linkToken || redeemed.current) return;
    redeemed.current = true;
    redeem.mutate(linkToken, {
      onSuccess: (s) => {
        set(s.token);
        router.replace(`/help/${slug}/tickets`);
      },
    });
  }, [linkToken, redeem, set, router, slug]);

  if (linkToken) {
    return (
      <div className="surface mx-auto max-w-md">
        {redeem.isError ? (
          <>
            <ErrorState error={redeem.error} title="This sign-in link does not work" />
            <div className="flex justify-center pb-6">
              <Button variant="outline" size="sm" onClick={() => router.replace(`/help/${slug}/signin`)}>
                Send me a new link
              </Button>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-3 px-6 py-14 text-center text-muted-foreground" aria-busy>
            <Loader2Icon className="size-6 animate-spin" />
            Signing you in...
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="surface mx-auto max-w-md p-6 sm:p-8">
      {request.isSuccess ? (
        <div className="text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary" style={{ background: "color-mix(in srgb, var(--primary) 14%, transparent)" }}>
            <MailCheckIcon className="size-6" />
          </span>
          <h1 className="mt-4 text-[20px] font-semibold tracking-[-0.02em]">Check your email</h1>
          <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">
            If {email} has a conversation with us, a sign-in link is on its way. It works once and expires soon.
          </p>
          <Button variant="ghost" size="sm" className="mt-4" onClick={() => request.reset()}>
            Use another email
          </Button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!email.trim()) return setError("Enter the email you wrote to us from.");
            setError(null);
            request.mutate(email.trim(), { onError: (err) => setError(errorMessage(err)) });
          }}
          className="space-y-4"
          noValidate
        >
          <div>
            <h1 className="text-[20px] font-semibold tracking-[-0.02em]">Sign in to your tickets</h1>
            <p className="mt-1 text-[13.5px] text-muted-foreground">No password: we email you a one-time link.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-email">Email</Label>
            <div className="relative">
              <MailIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
              <Input id="p-email" type="email" autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" className="h-10 pl-9" aria-invalid={!!error || undefined} />
            </div>
          </div>
          {error && <FieldError>{error}</FieldError>}
          <Button type="submit" size="lg" className="w-full" disabled={request.isPending}>
            {request.isPending ? "Sending..." : "Email me a sign-in link"}
          </Button>
        </form>
      )}
    </div>
  );
}

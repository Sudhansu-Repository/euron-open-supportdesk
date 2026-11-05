"use client";

import { CheckIcon, ChevronRightIcon, RocketIcon, XIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { usePermissions } from "@/features/auth/api";
import { useKnowledgeStats } from "@/features/knowledge/api";
import { useInboxes } from "@/features/settings/api";
import { useInvitations, useUsers } from "@/features/team/api";
import { useViewCounts } from "@/features/tickets/api";
import { cn } from "@/lib/cn";
import { useUiPrefs } from "@/lib/store";

import { onboardingProgress, onboardingSteps } from "./steps";

/** Four one-click steps to first value, shown to admins until done or hidden. */
export function OnboardingChecklist() {
  const { admin } = usePermissions();
  const hidden = useUiPrefs((s) => s.onboardingHidden);
  const hide = useUiPrefs((s) => s.hideOnboarding);
  const asked = useUiPrefs((s) => s.askedTestQuestion);
  const stats = useKnowledgeStats();
  const inboxes = useInboxes();
  const users = useUsers();
  const invitations = useInvitations(admin);
  const counts = useViewCounts();

  if (!admin || hidden || !stats.data || !inboxes.data || !users.data || !counts.data) return null;
  const widget = inboxes.data.find((i) => i.channel === "widget");
  const steps = onboardingSteps({
    sources: stats.data.sources,
    articles: stats.data.articles,
    widgetConfigured: !!widget && widget.allowed_origins.length > 0,
    widgetConversations: 0,
    teammates: users.data.length,
    invitations: invitations.data?.length ?? 0,
    conversations: counts.data.all,
    askedTestQuestion: asked,
  });
  const progress = onboardingProgress(steps);
  if (progress.complete) return null;

  return (
    <section aria-label="Get started" className="surface overflow-hidden">
      <div className="flex items-start gap-3 bg-gradient-to-br from-primary-soft to-transparent px-5 pt-5 pb-4">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <RocketIcon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold tracking-[-0.01em]">Set up your support desk</h2>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">
            {progress.done} of {progress.total} done. About five minutes to your first AI answer with sources.
          </p>
          <div className="mt-2.5 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-muted" aria-hidden>
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
        </div>
        <Button size="icon-xs" variant="subtle" aria-label="Hide the checklist" onClick={hide}>
          <XIcon />
        </Button>
      </div>
      <ol className="grid gap-2 p-3 sm:grid-cols-2">
        {steps.map((s, i) => (
          <li key={s.id}>
            <Link
              href={s.href}
              className={cn(
                "group flex h-full gap-3 rounded-xl px-3 py-3 transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                s.done ? "bg-muted/40" : "bg-muted/70 hover:bg-accent",
              )}
            >
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                  s.done ? "bg-savings text-white" : "bg-card text-muted-foreground shadow-[var(--elev-1)]",
                )}
              >
                {s.done ? <CheckIcon className="size-3.5" /> : i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn("block text-[13px] font-semibold", s.done && "text-muted-foreground line-through decoration-faint")}>{s.title}</span>
                <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">{s.body}</span>
                {!s.done && (
                  <span className="mt-1.5 inline-flex items-center gap-0.5 text-[12px] font-semibold text-primary">
                    {s.action} <ChevronRightIcon className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

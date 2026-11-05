"use client";

import { BookOpenIcon, TicketIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { ErrorState } from "@/components/error-state";
import { ThemeToggle } from "@/components/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { readableOn, safeColor } from "@/features/widget/state";
import { cn } from "@/lib/cn";

import { useHelpCenter } from "../api";

/** Load the website widget on help pages, the same way a customer's site does. */
function useWidget(widgetKey: string | null | undefined) {
  React.useEffect(() => {
    if (!widgetKey || document.getElementById("supportdesk-widget-loader")) return;
    const s = document.createElement("script");
    s.id = "supportdesk-widget-loader";
    s.src = "/widget.js";
    s.async = true;
    s.dataset.key = widgetKey;
    document.body.appendChild(s);
    return () => {
      s.remove();
      document.getElementById("supportdesk-widget")?.remove();
      (window as unknown as { __supportdeskWidget?: boolean }).__supportdeskWidget = false;
    };
  }, [widgetKey]);
}

/**
 * The public help center and customer portal frame: the company's title and accent
 * colour, links to articles and "my tickets", and the chat widget.
 */
export function HelpShell({ slug, children }: { slug: string; children: React.ReactNode }) {
  const help = useHelpCenter(slug);
  const pathname = usePathname();
  useWidget(help.data?.widget_key);
  const accent = safeColor(help.data?.accent_color);
  const style = { "--primary": accent, "--ring": accent, "--primary-foreground": readableOn(accent) } as React.CSSProperties;
  const inPortal = pathname.startsWith(`/help/${slug}/tickets`) || pathname.startsWith(`/help/${slug}/signin`);

  return (
    <div className="flex min-h-dvh flex-col bg-background" style={style}>
      <header className="sticky top-0 z-20 bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4 sm:px-6">
          <Link href={`/help/${slug}`} className="flex min-w-0 items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-ring">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary text-[13px] font-bold text-primary-foreground">
              {(help.data?.org_name ?? "?").charAt(0).toUpperCase()}
            </span>
            {help.data ? <span className="truncate text-[14.5px] font-semibold tracking-[-0.01em]">{help.data.org_name}</span> : <Skeleton className="h-4 w-32" />}
          </Link>
          <nav className="ml-auto flex items-center gap-1 text-[13px]" aria-label="Help center">
            <Link href={`/help/${slug}`} className={cn("inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium", !inPortal ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
              <BookOpenIcon className="size-4" /> <span className="hidden sm:inline">Articles</span>
            </Link>
            <Link href={`/help/${slug}/tickets`} className={cn("inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium", inPortal ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
              <TicketIcon className="size-4" /> My tickets
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-6 pb-24 sm:px-6">
        {help.isError ? (
          <div className="surface mx-auto max-w-lg">
            <ErrorState error={help.error} title="This help center is not available" />
          </div>
        ) : (
          children
        )}
      </main>
      <footer className="py-6 text-center text-[12px] text-faint">
        {help.data ? `${help.data.org_name} help center` : "Help center"} · Powered by SupportDesk
      </footer>
    </div>
  );
}

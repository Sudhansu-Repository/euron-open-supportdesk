"use client";

import { MenuIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { BrandLogo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useMe, useSetAvailability } from "@/features/auth/api";
import { useLive } from "@/features/live/agent-live";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

import { SidebarNav } from "./sidebar";
import { UserMenu } from "./user-menu";

/** Online or away. Routing assigns new conversations only to online agents. */
function AvailabilityToggle() {
  const { data: user } = useMe();
  const set = useSetAvailability();
  const online = user?.availability === "online";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            role="switch"
            aria-checked={online}
            aria-label={online ? "You are online. Switch to away" : "You are away. Switch to online"}
            onClick={() =>
              set.mutate(online ? "away" : "online", {
                onSuccess: (u) => toast.success(u.availability === "online" ? "You are online: new conversations can reach you." : "You are away: new conversations go to teammates."),
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
            className="inline-flex h-8 items-center gap-2 rounded-full bg-muted px-3 text-[12.5px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          />
        }
      >
        <span className={cn("size-2 rounded-full", online ? "bg-savings" : "bg-warning")} aria-hidden />
        {online ? "Online" : "Away"}
      </TooltipTrigger>
      <TooltipContent>
        {online ? "New conversations are routed to you when you have capacity." : "You keep your conversations, but new ones go to online teammates."}
      </TooltipContent>
    </Tooltip>
  );
}

/** Whether live updates are flowing. When not, views poll every few seconds instead. */
function LiveIndicator() {
  const { status } = useLive();
  const open = status === "open";
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="hidden items-center gap-1.5 rounded-full px-2 py-1 text-[11.5px] text-subtle focus-visible:outline-2 focus-visible:outline-ring sm:inline-flex" />}>
        <span className="relative flex size-2">
          {open && <span className="absolute inline-flex size-full animate-ping rounded-full bg-savings opacity-40" />}
          <span className={cn("relative inline-flex size-2 rounded-full", open ? "bg-savings" : status === "connecting" ? "bg-faint" : "bg-warning")} />
        </span>
        {open ? "Live" : status === "connecting" ? "Connecting" : "Reconnecting"}
      </TooltipTrigger>
      <TooltipContent>
        {open ? "New messages appear as they arrive." : "Live updates are reconnecting. The inbox refreshes every 10 seconds meanwhile."}
      </TooltipContent>
    </Tooltip>
  );
}

export function Topbar() {
  const [menuOpen, setMenuOpen] = React.useState(false);
  return (
    <header className="sticky top-0 z-30 bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/70">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
        <Button variant="subtle" size="icon" className="-ml-2 lg:hidden" aria-label="Open navigation" onClick={() => setMenuOpen(true)}>
          <MenuIcon />
        </Button>
        <Link href="/inbox" className="rounded-lg lg:hidden" aria-label="SupportDesk inbox">
          <BrandLogo collapsed />
        </Link>
        <div className="ml-auto flex items-center gap-1.5">
          <LiveIndicator />
          <AvailabilityToggle />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="bg-sidebar">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-14 items-center px-4">
            <BrandLogo />
          </div>
          <div className="overflow-y-auto px-3 pb-6">
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}

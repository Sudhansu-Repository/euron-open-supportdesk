"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

/**
 * Persisted UI preferences only (never server data). Rehydrated after mount so the
 * first client render matches the server render. The theme itself is persisted by
 * next-themes.
 */
interface UiPrefs {
  sidebarCollapsed: boolean;
  settingsOpen: boolean;
  onboardingHidden: boolean;
  askedTestQuestion: boolean;
  toggleSidebar: () => void;
  setSettingsOpen: (open: boolean) => void;
  hideOnboarding: () => void;
  markTestQuestion: () => void;
}

export const useUiPrefs = create<UiPrefs>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      settingsOpen: false,
      onboardingHidden: false,
      askedTestQuestion: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSettingsOpen: (open) => set({ settingsOpen: open }),
      hideOnboarding: () => set({ onboardingHidden: true }),
      markTestQuestion: () => set({ askedTestQuestion: true }),
    }),
    {
      name: "supportdesk.ui",
      version: 2,
      skipHydration: true,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, settingsOpen: s.settingsOpen, onboardingHidden: s.onboardingHidden, askedTestQuestion: s.askedTestQuestion }),
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<UiPrefs>;
        const bool = (v: unknown, d: boolean) => (typeof v === "boolean" ? v : d);
        return {
          ...current,
          sidebarCollapsed: bool(p.sidebarCollapsed, current.sidebarCollapsed),
          settingsOpen: bool(p.settingsOpen, current.settingsOpen),
          onboardingHidden: bool(p.onboardingHidden, current.onboardingHidden),
          askedTestQuestion: bool(p.askedTestQuestion, current.askedTestQuestion),
        };
      },
    },
  ),
);

/** Who is typing where, from live events. Not persisted: it expires in seconds. */
interface TypingState {
  byTicket: Record<string, number>;
  mark: (ticketId: string) => void;
}

export const useTyping = create<TypingState>()((set) => ({
  byTicket: {},
  mark: (ticketId) => set((s) => ({ byTicket: { ...s.byTicket, [ticketId]: Date.now() } })),
}));

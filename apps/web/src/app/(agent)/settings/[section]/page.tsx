import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SettingsScreen } from "@/features/settings/components/settings-screen";
import { SETTINGS_ITEMS } from "@/lib/nav";

export async function generateMetadata({ params }: { params: Promise<{ section: string }> }): Promise<Metadata> {
  const { section } = await params;
  const item = SETTINGS_ITEMS.find((i) => i.href === `/settings/${section}`);
  return { title: item ? item.label : "Settings" };
}

export default async function SettingsPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!SETTINGS_ITEMS.some((i) => i.href === `/settings/${section}`)) notFound();
  return <SettingsScreen section={section} />;
}

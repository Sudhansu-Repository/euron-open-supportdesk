import type { Metadata } from "next";

import { HelpHome } from "@/features/help/components/help-home";

export const metadata: Metadata = { title: "Help center" };

export default async function HelpPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <HelpHome slug={slug} />;
}

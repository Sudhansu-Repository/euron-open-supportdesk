import type { Metadata } from "next";

import { GapDetailScreen } from "@/features/gaps/components/gap-detail";

export const metadata: Metadata = { title: "Knowledge gap" };

export default async function GapPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GapDetailScreen id={id} />;
}

import type { Metadata } from "next";

import { PortalTickets } from "@/features/portal/components/portal-tickets";

export const metadata: Metadata = { title: "My tickets" };

export default async function PortalTicketsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <PortalTickets slug={slug} />;
}

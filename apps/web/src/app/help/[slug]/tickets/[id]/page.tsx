import type { Metadata } from "next";

import { PortalTicket } from "@/features/portal/components/portal-ticket";

export const metadata: Metadata = { title: "Ticket" };

export default async function PortalTicketPage({ params }: { params: Promise<{ slug: string; id: string }> }) {
  const { slug, id } = await params;
  return <PortalTicket slug={slug} id={id} />;
}

import type { Metadata } from "next";

import { PortalNewTicket } from "@/features/portal/components/portal-new-ticket";

export const metadata: Metadata = { title: "New ticket" };

export default async function PortalNewTicketPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <PortalNewTicket slug={slug} />;
}

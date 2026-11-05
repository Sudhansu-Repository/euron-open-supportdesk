import type { Metadata } from "next";
import { Suspense } from "react";

import { InboxScreen } from "@/features/tickets/components/inbox-screen";

export const metadata: Metadata = { title: "Conversation" };

export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <InboxScreen selectedId={id} />
    </Suspense>
  );
}

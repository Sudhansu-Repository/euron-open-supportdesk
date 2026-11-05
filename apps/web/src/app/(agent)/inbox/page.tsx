import type { Metadata } from "next";
import { Suspense } from "react";

import { InboxScreen } from "@/features/tickets/components/inbox-screen";

export const metadata: Metadata = { title: "Inbox" };

export default function InboxPage() {
  return (
    <Suspense>
      <InboxScreen selectedId={null} />
    </Suspense>
  );
}

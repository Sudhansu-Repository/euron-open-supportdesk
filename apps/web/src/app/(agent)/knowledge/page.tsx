import type { Metadata } from "next";
import { Suspense } from "react";

import { KnowledgeScreen } from "@/features/knowledge/components/knowledge-screen";

export const metadata: Metadata = { title: "Knowledge" };

export default function KnowledgePage() {
  return (
    <Suspense>
      <KnowledgeScreen />
    </Suspense>
  );
}

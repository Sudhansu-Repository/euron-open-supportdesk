import type { Metadata } from "next";
import { Suspense } from "react";

import { AnalyticsScreen } from "@/features/analytics/components/analytics-screen";

export const metadata: Metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <Suspense>
      <AnalyticsScreen />
    </Suspense>
  );
}

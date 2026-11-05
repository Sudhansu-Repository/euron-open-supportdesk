import type { Metadata, Viewport } from "next";
import { Suspense } from "react";

import { WidgetFrame } from "@/features/widget/components/widget-frame";

export const metadata: Metadata = { title: "Support chat", robots: { index: false, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

/**
 * The chat inside the website widget's iframe. middleware.ts sets its
 * Content-Security-Policy frame-ancestors to the inbox's allowed sites.
 */
export default function WidgetFramePage() {
  return (
    <Suspense>
      <WidgetFrame />
    </Suspense>
  );
}

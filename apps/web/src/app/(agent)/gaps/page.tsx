import type { Metadata } from "next";

import { GapsScreen } from "@/features/gaps/components/gaps-screen";

export const metadata: Metadata = { title: "Knowledge gaps" };

export default function GapsPage() {
  return <GapsScreen />;
}

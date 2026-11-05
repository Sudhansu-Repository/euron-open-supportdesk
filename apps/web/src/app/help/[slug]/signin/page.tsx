import type { Metadata } from "next";
import { Suspense } from "react";

import { PortalSignin } from "@/features/portal/components/portal-signin";

export const metadata: Metadata = { title: "Sign in" };

export default async function PortalSigninPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <Suspense>
      <PortalSignin slug={slug} />
    </Suspense>
  );
}

import type { Metadata } from "next";

import { CustomerProfile } from "@/features/customers/components/customer-profile";

export const metadata: Metadata = { title: "Customer" };

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CustomerProfile id={id} />;
}

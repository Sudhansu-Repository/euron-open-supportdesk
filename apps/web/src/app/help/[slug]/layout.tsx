import { HelpShell } from "@/features/help/components/help-shell";

export default async function HelpLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <HelpShell slug={slug}>{children}</HelpShell>;
}

import type { Metadata } from "next";

import { HelpArticle } from "@/features/help/components/help-article";

export const metadata: Metadata = { title: "Article" };

export default async function HelpArticlePage({ params }: { params: Promise<{ slug: string; articleSlug: string }> }) {
  const { slug, articleSlug } = await params;
  return <HelpArticle slug={slug} articleSlug={articleSlug} />;
}

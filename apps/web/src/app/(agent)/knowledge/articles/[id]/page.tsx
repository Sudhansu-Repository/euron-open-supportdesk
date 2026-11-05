import type { Metadata } from "next";
import { Suspense } from "react";

import { ArticleEditor } from "@/features/knowledge/components/article-editor";

export const metadata: Metadata = { title: "Article" };

export default async function ArticlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <ArticleEditor id={id} />
    </Suspense>
  );
}

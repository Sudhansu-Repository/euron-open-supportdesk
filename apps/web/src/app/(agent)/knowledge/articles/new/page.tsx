import type { Metadata } from "next";
import { Suspense } from "react";

import { ArticleEditor } from "@/features/knowledge/components/article-editor";

export const metadata: Metadata = { title: "New article" };

export default function NewArticlePage() {
  return (
    <Suspense>
      <ArticleEditor id={null} />
    </Suspense>
  );
}

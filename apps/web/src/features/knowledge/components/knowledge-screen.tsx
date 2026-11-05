"use client";

import { BookOpenIcon, DatabaseIcon, FileTextIcon, FlaskConicalIcon, LayersIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/features/auth/api";
import { formatNumber } from "@/lib/format";

import { useKnowledgeStats } from "../api";

import { ArticlesTab } from "./articles-tab";
import { PlaygroundTab } from "./playground-tab";
import { SourcesTab } from "./sources-tab";

const TABS = ["sources", "articles", "test"] as const;
type Tab = (typeof TABS)[number];

/** What the AI knows: sources and articles, how they are indexed, and a playground. */
export function KnowledgeScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const stats = useKnowledgeStats();
  const { admin } = usePermissions();
  const raw = params.get("tab");
  const tab: Tab = (TABS as readonly string[]).includes(raw ?? "") ? (raw as Tab) : "sources";

  return (
    <div>
      <PageHeader
        title="Knowledge"
        description={
          <>
            The AI answers only from what is here, and cites it. Upload documents, add web pages, or write articles. <Hint term="rag" />
          </>
        }
        actions={
          admin && (
            <Button nativeButton={false} render={<Link href="/knowledge/articles/new" />}>
              <PlusIcon /> New article
            </Button>
          )
        }
      />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Sources"
          icon={DatabaseIcon}
          loading={stats.isLoading}
          value={formatNumber(stats.data?.sources)}
          detail={stats.data ? `${stats.data.ready} ready${stats.data.processing ? `, ${stats.data.processing} indexing` : ""}${stats.data.failed ? `, ${stats.data.failed} failed` : ""}` : undefined}
          tone={stats.data?.failed ? "warn" : "default"}
        />
        <Stat label="Articles" icon={FileTextIcon} loading={stats.isLoading} value={formatNumber(stats.data?.articles)} detail={stats.data ? `${stats.data.published} published` : undefined} />
        <Stat label="Passages indexed" icon={LayersIcon} loading={stats.isLoading} value={formatNumber(stats.data?.chunks)} detail="What retrieval searches." />
        <Stat
          label="Knowledge version"
          icon={BookOpenIcon}
          loading={stats.isLoading}
          value={stats.data ? `v${stats.data.kb_version}` : "n/a"}
          detail={stats.data ? `Embedder: ${stats.data.embedder}` : undefined}
        />
      </div>
      <Tabs value={tab} onValueChange={(v) => router.replace(`${pathname}?tab=${String(v)}`, { scroll: false })}>
        <TabsList>
          <TabsTrigger value="sources">
            <DatabaseIcon /> Sources
          </TabsTrigger>
          <TabsTrigger value="articles">
            <FileTextIcon /> Articles
          </TabsTrigger>
          <TabsTrigger value="test">
            <FlaskConicalIcon /> Test a question
          </TabsTrigger>
        </TabsList>
        <TabsContent value="sources">
          <SourcesTab />
        </TabsContent>
        <TabsContent value="articles">
          <ArticlesTab />
        </TabsContent>
        <TabsContent value="test">
          <PlaygroundTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

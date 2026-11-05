"use client";

import { ArrowLeftIcon, EyeIcon, LightbulbIcon, Loader2Icon, PencilIcon, SendIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { ErrorState } from "@/components/error-state";
import { Markdown } from "@/components/markdown";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { useDraftFromGap } from "@/features/gaps/api";
import { useSettings } from "@/features/settings/api";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { useArticle, useDeleteArticle, useSaveArticle } from "../api";

/**
 * Write an article in Markdown with a live preview. Opened from a knowledge gap
 * (`?gap=<id>`), it starts from a draft built out of the agent replies that resolved the
 * gap, and publishing it closes the gap.
 */
export function ArticleEditor({ id }: { id: string | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const gapId = id ? null : params.get("gap");
  const article = useArticle(id);
  const save = useSaveArticle();
  const remove = useDeleteArticle();
  const fromGap = useDraftFromGap();
  const settings = useSettings();
  const { admin } = usePermissions();
  const [title, setTitle] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [body, setBody] = React.useState("");
  const [view, setView] = React.useState<"write" | "preview">("write");
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [noAnswers, setNoAnswers] = React.useState(false);
  const loaded = React.useRef(false);
  const gapRequested = React.useRef(false);

  React.useEffect(() => {
    if (article.data && !loaded.current) {
      loaded.current = true;
      setTitle(article.data.title);
      setCategory(article.data.category ?? "");
      setBody(article.data.body);
    }
  }, [article.data]);

  React.useEffect(() => {
    if (!gapId || gapRequested.current) return;
    gapRequested.current = true;
    fromGap.mutate(gapId, {
      onSuccess: (d) => {
        setTitle((t) => t || d.title);
        if (d.source === "none" || !d.body.trim()) setNoAnswers(true);
        else setBody((b) => b || d.body);
      },
      onError: (e) => toast.error(`Could not draft from the gap: ${errorMessage(e)}`),
    });
  }, [gapId, fromGap]);

  function submit(status: "draft" | "published") {
    if (!title.trim() || !body.trim()) {
      toast.error("Give the article a title and some text first.");
      return;
    }
    save.mutate(
      { id: id ?? undefined, body: { title: title.trim(), body, category: category.trim() || null, status, gap_id: gapId } },
      {
        onSuccess: (a) => {
          toast.success(
            status === "published"
              ? gapId
                ? "Published. The gap is closed and the AI can answer this from now on."
                : "Published. The AI uses it from the next question, and it is live in your help center."
              : "Draft saved. It is not used by the AI until you publish it.",
          );
          if (!id) router.replace(`/knowledge/articles/${a.id}`);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  if (id && article.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[480px]" />
      </div>
    );
  }
  if (id && (article.isError || !article.data)) {
    return (
      <Surface>
        <ErrorState error={article.error} title="Could not open this article" onRetry={() => void article.refetch()} />
      </Surface>
    );
  }

  const published = article.data?.status === "published";
  const categories = settings.data?.categories ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/knowledge?tab=articles" className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
          <ArrowLeftIcon className="size-3.5" /> Articles
        </Link>
        {article.data && (
          <Chip tone={published ? "success" : "neutral"} dot>
            {published ? `Published ${formatRelative(article.data.published_at)}` : "Draft"}
          </Chip>
        )}
        {gapId && (
          <Chip tone="ai">
            <LightbulbIcon /> From a knowledge gap
          </Chip>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {id && admin && (
            <Button variant="destructive-soft" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2Icon /> Delete
            </Button>
          )}
          <Button variant="outline" size="sm" disabled={save.isPending || !admin} onClick={() => submit("draft")}>
            {published ? "Unpublish" : "Save draft"}
          </Button>
          <Button size="sm" disabled={save.isPending || !admin} onClick={() => submit("published")}>
            {save.isPending ? <Loader2Icon className="animate-spin" /> : <SendIcon />} {published ? "Update" : "Publish"}
          </Button>
        </div>
      </div>

      {fromGap.isPending && (
        <div className="flex items-center gap-2 rounded-xl bg-ai-soft px-4 py-3 text-[13px] text-ai">
          <Loader2Icon className="size-4 animate-spin" /> Drafting from the questions and the replies that resolved them...
        </div>
      )}

      {noAnswers && !body.trim() && (
        <div role="note" className="rounded-xl bg-warning-soft px-4 py-3 text-[13px] text-warning">
          No agent has answered these questions yet: write the answer, or reply to one of the conversations first.
        </div>
      )}

      <Surface className="space-y-4 p-5">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_240px]">
          <Field label="Title" htmlFor="a-title" hint="Write it like the question customers ask.">
            <Input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="How do I reset my password?" className="h-10 text-[15px] font-medium" />
          </Field>
          <Field label="Category" htmlFor="a-cat" hint="Groups articles in the help center.">
            <Input id="a-cat" list="article-categories" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="account" />
            <datalist id="article-categories">
              {categories.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </datalist>
          </Field>
        </div>
        <div>
          <div className="mb-2 flex items-center gap-2 lg:hidden">
            <div role="tablist" aria-label="Editor view" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">
              {(["write", "preview"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={cn("inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium text-muted-foreground", view === v && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent")}
                >
                  {v === "write" ? <PencilIcon className="size-3.5" /> : <EyeIcon className="size-3.5" />}
                  {v === "write" ? "Write" : "Preview"}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={cn(view === "preview" && "hidden lg:block")}>
              <div className="mb-1.5 hidden text-[12px] font-medium text-muted-foreground lg:block">Markdown</div>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                aria-label="Article body in Markdown"
                placeholder={"## Steps\n\n1. Open Settings\n2. Choose Security\n\nUse headings: the AI cites them as sources."}
                className="min-h-[440px] font-mono text-[13px] leading-relaxed"
              />
            </div>
            <div className={cn(view === "write" && "hidden lg:block")}>
              <div className="mb-1.5 hidden text-[12px] font-medium text-muted-foreground lg:block">Preview</div>
              <div className="min-h-[440px] rounded-lg bg-muted/40 px-5 py-4">
                {body.trim() ? (
                  <>
                    <h1 className="mb-3 text-[20px] font-semibold tracking-[-0.02em]">{title || "Untitled"}</h1>
                    <Markdown source={body} />
                  </>
                ) : (
                  <p className="text-[13px] text-subtle">The preview shows the article as customers see it in the help center.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </Surface>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this article?"
        description="It leaves the help center and the AI stops using it right away."
        confirmLabel="Delete article"
        pending={remove.isPending}
        onConfirm={() =>
          id &&
          remove.mutate(id, {
            onSuccess: () => {
              toast.success("Article deleted.");
              router.replace("/knowledge?tab=articles");
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </div>
  );
}

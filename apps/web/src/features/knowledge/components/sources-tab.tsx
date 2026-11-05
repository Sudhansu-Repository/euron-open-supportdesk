"use client";

import { FileUpIcon, GlobeIcon, LayersIcon, Loader2Icon, MoreHorizontalIcon, RefreshCwIcon, Trash2Icon, UploadCloudIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { Source } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatBytes, formatNumber, formatRelative } from "@/lib/format";
import { humanize, type Tone } from "@/lib/labels";
import { obj, str, num } from "@/lib/read";

import { isWorking, useAddUrl, useChunks, useDeleteSource, useReindex, useSources, useUploadSource } from "../api";

export const ACCEPT = ".pdf,.docx,.md,.markdown,.txt,.html,.htm,.csv";
const MAX_MB = 25;

export function sourceStatus(status: string): { label: string; tone: Tone } {
  if (status === "ready") return { label: "Ready", tone: "success" };
  if (status === "failed") return { label: "Failed", tone: "danger" };
  if (status === "queued") return { label: "Queued", tone: "neutral" };
  if (isWorking(status)) return { label: "Indexing", tone: "info" };
  return { label: humanize(status), tone: "neutral" };
}

/** Files the upload accepts, by extension; anything else is refused before upload. */
export function acceptedFile(name: string): boolean {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  return ["pdf", "docx", "md", "markdown", "txt", "html", "htm", "csv"].includes(ext);
}

function UrlDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const add = useAddUrl();
  const [url, setUrl] = React.useState("");
  const [sitemap, setSitemap] = React.useState(false);
  const [title, setTitle] = React.useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a web page or sitemap</DialogTitle>
          <DialogDescription>SupportDesk fetches the page (or every page in the sitemap, up to the server limit), respects robots.txt, and indexes the text.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(
              { url: url.trim(), sitemap, title: title.trim() || null },
              {
                onSuccess: () => {
                  toast.success("Added. Indexing runs in the background.");
                  setUrl("");
                  setTitle("");
                  setSitemap(false);
                  onOpenChange(false);
                },
                onError: (err) => toast.error(errorMessage(err)),
              },
            );
          }}
        >
          <DialogBody className="space-y-4">
            <Field label="URL" htmlFor="src-url" hint="A public https:// address. Private and internal addresses are refused.">
              <Input id="src-url" type="url" required placeholder="https://docs.example.com/getting-started" value={url} onChange={(e) => setUrl(e.target.value)} />
            </Field>
            <Field label="Title (optional)" htmlFor="src-title" hint="Shown in citations. Defaults to the page title.">
              <Input id="src-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 px-3 py-2.5 text-[13px]">
              <span>
                <span className="font-medium">This is a sitemap</span>
                <span className="block text-[12px] text-muted-foreground">Index every page it lists, like /sitemap.xml.</span>
              </span>
              <Switch checked={sitemap} onCheckedChange={setSitemap} />
            </label>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={add.isPending || !url.trim()}>
              {add.isPending ? "Adding..." : "Add and index"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChunksSheet({ source, onOpenChange }: { source: Source | null; onOpenChange: (o: boolean) => void }) {
  const chunks = useChunks(source?.id ?? null);
  return (
    <Sheet open={!!source} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{source?.title}</SheetTitle>
          <SheetDescription>The passages retrieval searches, in order. The AI quotes and cites these, nothing else.</SheetDescription>
        </SheetHeader>
        <SheetBody>
          {chunks.isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
          ) : chunks.isError ? (
            <ErrorState compact error={chunks.error} onRetry={() => void chunks.refetch()} />
          ) : !chunks.data?.length ? (
            <EmptyState compact icon={LayersIcon} title="No passages yet" description="This source has not been indexed yet, or produced no text. Reindex it once it is fixed." />
          ) : (
            <ol className="space-y-3">
              {chunks.data.map((raw, i) => {
                const c = obj(raw);
                return (
                  <li key={str(c.id) ?? i} className="rounded-xl bg-muted/60 p-3.5">
                    <div className="mb-1.5 flex items-center gap-2 text-[11.5px] text-subtle">
                      <span className="font-semibold text-foreground">#{(num(c.ordinal) ?? i) + 1}</span>
                      {str(c.heading) && <span className="truncate">{str(c.heading)}</span>}
                      <span className="ml-auto tabular">{num(c.tokens) ?? 0} tokens</span>
                    </div>
                    <p className="text-[12.5px] leading-relaxed whitespace-pre-wrap">{str(c.text)}</p>
                  </li>
                );
              })}
            </ol>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

export function SourcesTab() {
  const sources = useSources();
  const upload = useUploadSource();
  const reindex = useReindex();
  const remove = useDeleteSource();
  const { admin } = usePermissions();
  const [urlOpen, setUrlOpen] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState<string[]>([]);
  const [chunksOf, setChunksOf] = React.useState<Source | null>(null);
  const [deleting, setDeleting] = React.useState<Source | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function uploadFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      if (!acceptedFile(file.name)) {
        toast.error(`${file.name}: use PDF, DOCX, Markdown, text, HTML, or a CSV of question,answer rows.`);
        continue;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`${file.name} is larger than ${MAX_MB} MB. Split it or upload the text instead.`);
        continue;
      }
      setUploading((u) => [...u, file.name]);
      try {
        await upload.mutateAsync({ file });
        toast.success(`${file.name} uploaded. Indexing runs in the background.`);
      } catch (e) {
        toast.error(`${file.name}: ${errorMessage(e)}`);
      } finally {
        setUploading((u) => u.filter((n) => n !== file.name));
      }
    }
  }

  const rows = sources.data ?? [];

  return (
    <div className="space-y-5">
      {admin && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void uploadFiles(e.dataTransfer.files);
          }}
          className={cn(
            "flex flex-col items-center gap-3 rounded-2xl bg-card px-6 py-7 text-center shadow-[var(--elev-2)] transition-colors sm:flex-row sm:text-left",
            dragging && "bg-primary-soft",
          )}
        >
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <UploadCloudIcon className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold">Drop files to teach the AI</div>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">
              PDF, Word (DOCX), Markdown, text, HTML, or an FAQ as CSV with <code className="rounded bg-muted px-1 font-mono text-[11.5px]">question,answer</code> rows. Up to {MAX_MB} MB each.
            </p>
            {uploading.length > 0 && (
              <p className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-primary">
                <Loader2Icon className="size-3.5 animate-spin" /> Uploading {uploading.join(", ")}
              </p>
            )}
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <input ref={fileRef} type="file" multiple accept={ACCEPT} className="sr-only" aria-label="Choose files to upload" onChange={(e) => e.target.files && void uploadFiles(e.target.files)} />
            <Button onClick={() => fileRef.current?.click()} disabled={uploading.length > 0}>
              <FileUpIcon /> Upload files
            </Button>
            <Button variant="outline" onClick={() => setUrlOpen(true)}>
              <GlobeIcon /> Add URL
            </Button>
          </div>
        </div>
      )}

      <Surface>
        <SurfaceHeader title="Sources" description="Each source is fetched, split into passages and embedded by the worker. Status updates live." />
        {sources.isLoading ? (
          <TableSkeleton rows={5} cols={6} />
        ) : sources.isError ? (
          <ErrorState error={sources.error} title="Could not load sources" onRetry={() => void sources.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={UploadCloudIcon}
            title="The AI knows nothing yet"
            description="Without sources the AI cannot answer and hands every question to your team. Upload your help docs or an FAQ CSV to start."
            action={
              admin ? (
                <Button size="sm" onClick={() => fileRef.current?.click()}>
                  <FileUpIcon /> Upload your first document
                </Button>
              ) : (
                <span className="text-[12.5px] text-muted-foreground">Ask an admin to add the first documents.</span>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Passages</TableHead>
                <TableHead className="hidden text-right md:table-cell">Size</TableHead>
                <TableHead className="hidden lg:table-cell">Indexed</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((s) => {
                const st = sourceStatus(s.status);
                return (
                  <TableRow key={s.id}>
                    <TableCell className="max-w-[320px]">
                      <div className="truncate font-medium">{s.title}</div>
                      <div className="truncate text-[12px] text-muted-foreground">
                        {humanize(s.kind)}
                        {s.url ? ` · ${s.url}` : s.filename ? ` · ${s.filename}` : ""}
                      </div>
                      {s.status === "failed" && s.error && <div className="mt-1 text-[12px] text-danger">{s.error}</div>}
                    </TableCell>
                    <TableCell>
                      <Chip tone={st.tone}>
                        {isWorking(s.status) && <Loader2Icon className="animate-spin" />}
                        {st.label}
                      </Chip>
                    </TableCell>
                    <TableCell className="text-right tabular">{formatNumber(s.chunk_count)}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular md:table-cell">{s.size ? formatBytes(s.size) : s.pages ? `${s.pages} pages` : "n/a"}</TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{s.last_indexed_at ? formatRelative(s.last_indexed_at) : "Not yet"}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger render={<Button variant="subtle" size="icon-xs" aria-label={`Actions for ${s.title}`} />}>
                          <MoreHorizontalIcon />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onClick={() => setChunksOf(s)} disabled={!admin}>
                            <LayersIcon /> View passages
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={!admin || isWorking(s.status)}
                            onClick={() =>
                              reindex.mutate(s.id, { onSuccess: () => toast.success("Reindexing. Cached answers from the old version are dropped."), onError: (e) => toast.error(errorMessage(e)) })
                            }
                          >
                            <RefreshCwIcon /> Reindex
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive" disabled={!admin} onClick={() => setDeleting(s)}>
                            <Trash2Icon /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Surface>
      <UrlDialog open={urlOpen} onOpenChange={setUrlOpen} />
      <ChunksSheet source={chunksOf} onOpenChange={(o) => !o && setChunksOf(null)} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.title ?? "this source"}?`}
        description="Its passages leave the index right away, and the AI stops citing it. Cached answers built on it are dropped."
        confirmLabel="Delete source"
        pending={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success("Source deleted.");
              setDeleting(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </div>
  );
}

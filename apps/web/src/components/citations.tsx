import { ExternalLinkIcon, FileTextIcon } from "lucide-react";

import type { Citation } from "@/lib/api/types";
import { cn } from "@/lib/cn";

/** "Title > Heading", or just the title. */
export function citationLabel(c: Pick<Citation, "title" | "heading">): string {
  return c.heading && c.heading !== c.title ? `${c.title} > ${c.heading}` : c.title;
}

/** Only http(s) links are followed; anything else renders as plain text. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

/** The sources an AI answer cites, under the message. */
export function Citations({ citations, className, showRelevance = false }: { citations: Citation[]; className?: string; showRelevance?: boolean }) {
  if (!citations.length) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <span className="text-[11px] font-medium text-subtle">Sources</span>
      {citations.map((c, i) => {
        const href = safeHref(c.url);
        const body = (
          <>
            <FileTextIcon className="size-3 shrink-0" />
            <span className="max-w-[260px] truncate">{citationLabel(c)}</span>
            {showRelevance && c.relevance != null && <span className="text-subtle tabular">{c.relevance.toFixed(2)}</span>}
            {href && <ExternalLinkIcon className="size-3 shrink-0 opacity-60" />}
          </>
        );
        const cls = "inline-flex max-w-full items-center gap-1 rounded-full bg-card px-2 py-0.5 text-[11.5px] text-muted-foreground shadow-[var(--elev-1)]";
        return href ? (
          <a key={`${c.chunk_id ?? i}`} href={href} target="_blank" rel="noopener noreferrer nofollow" className={cn(cls, "hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring")}>
            {body}
          </a>
        ) : (
          <span key={`${c.chunk_id ?? i}`} className={cls}>
            {body}
          </span>
        );
      })}
    </div>
  );
}

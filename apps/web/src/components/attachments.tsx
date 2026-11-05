import { DownloadIcon, PaperclipIcon } from "lucide-react";

import type { TicketDetail } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

type Attachment = TicketDetail["attachments"][number];

/** Files on a conversation, each a download through the API (agent cookie, same origin). */
export function AttachmentList({ items, className }: { items: Attachment[]; className?: string }) {
  if (!items.length) return null;
  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)} aria-label="Attachments">
      {items.map((a) => (
        <li key={a.id}>
          <a
            href={`/api/v1/attachments/${a.id}`}
            download={a.filename}
            className="group inline-flex max-w-full items-center gap-1.5 rounded-lg bg-card px-2.5 py-1.5 text-[12px] shadow-[var(--elev-1)] hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
          >
            <PaperclipIcon className="size-3.5 shrink-0 text-subtle" />
            <span className="max-w-[220px] truncate font-medium">{a.filename}</span>
            <span className="shrink-0 text-subtle tabular">{formatBytes(a.size)}</span>
            <DownloadIcon className="size-3.5 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
          </a>
        </li>
      ))}
    </ul>
  );
}

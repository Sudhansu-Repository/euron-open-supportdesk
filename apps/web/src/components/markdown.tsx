import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

/**
 * Only http(s), mailto and in-page links survive; anything else (javascript:, data:)
 * becomes an empty href. react-markdown's own transform already drops dangerous schemes;
 * this narrows it further for articles and messages written by other people.
 */
export function safeUrl(url: string): string {
  const cleaned = defaultUrlTransform(url);
  if (!cleaned) return "";
  if (cleaned.startsWith("#") || cleaned.startsWith("/")) return cleaned;
  return /^(https?:|mailto:)/i.test(cleaned) ? cleaned : "";
}

/**
 * GitHub-flavoured Markdown for articles and messages. Raw HTML in the source is not
 * rendered (skipHtml), so content cannot inject scripts, styles or frames.
 */
export function Markdown({ source, className, compact = false }: { source: string; className?: string; compact?: boolean }) {
  return (
    <div className={cn("prose-sd", compact && "prose-compact", className)}>
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        urlTransform={safeUrl}
        components={{
          a: ({ href, children }) => (
            <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer nofollow">
              {children}
            </a>
          ),
          img: ({ src, alt }) =>
            typeof src === "string" && safeUrl(src) ? (
              // Article images are authored URLs unknown at build time, so next/image cannot optimise them.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={safeUrl(src)} alt={alt ?? ""} className="max-w-full rounded-lg" loading="lazy" />
            ) : null,
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

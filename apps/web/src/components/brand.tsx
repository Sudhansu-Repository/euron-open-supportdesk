import { cn } from "@/lib/cn";

/** The SupportDesk mark: a speech bubble with an AI spark, in the accent colour. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7", className)}>
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M9 11.5A3.5 3.5 0 0 1 12.5 8h7A3.5 3.5 0 0 1 23 11.5v5a3.5 3.5 0 0 1-3.5 3.5H15l-4.2 3.3c-.5.4-1.1 0-1.1-.6V20.2A3.5 3.5 0 0 1 9 17.6z"
        fill="none"
        className="stroke-primary-foreground"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M16 10.6l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" className="fill-primary-foreground" />
    </svg>
  );
}

export function BrandLogo({ collapsed = false, className }: { collapsed?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark />
      {!collapsed && <span className="text-[15px] font-semibold tracking-[-0.02em]">SupportDesk</span>}
    </span>
  );
}

import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

const HUES = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5", "bg-chart-6"] as const;

/** A stable colour per name, so the same agent or customer always looks the same. */
export function avatarHue(seed: string): (typeof HUES)[number] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return HUES[h % HUES.length] ?? HUES[0];
}

export function Avatar({ name, size = "md", className, title }: { name: string | null | undefined; size?: "xs" | "sm" | "md" | "lg"; className?: string; title?: string }) {
  const n = name || "?";
  return (
    <span
      title={title ?? n}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white select-none",
        avatarHue(n),
        size === "xs" && "size-5 text-[9px]",
        size === "sm" && "size-6 text-[10px]",
        size === "md" && "size-8 text-[11.5px]",
        size === "lg" && "size-11 text-[15px]",
        className,
      )}
      aria-hidden={title ? undefined : true}
    >
      {initials(n)}
    </span>
  );
}

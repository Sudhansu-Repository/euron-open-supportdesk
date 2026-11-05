/**
 * Number, money, token, duration and date formatting used everywhere a figure is shown.
 * The API sends money as decimal strings (exact), so every money helper accepts both.
 */

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function trim(n: number): string {
  const fixed = n >= 100 ? n.toFixed(0) : n.toFixed(1);
  return fixed.replace(/\.0$/, "");
}

/** 14,923. */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return intFmt.format(value);
}

/** A 0..1 ratio as a percentage: 0.2462 becomes 24.6%. */
export function formatRatio(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return formatPercent(value * 100, digits);
}

/** A value already in percent: 60.4 becomes 60.4%. Whole numbers drop the decimal. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const fixed = value.toFixed(digits);
  return `${fixed.replace(/\.0+$/, "")}%`;
}

/** 812 B, 4.2 KB, 12 MB. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return "n/a";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${trim(bytes / 1024)} KB`;
  return `${trim(bytes / (1024 * 1024))} MB`;
}

const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateTimeFmt.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateFmt.format(d);
}

/** "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "n/a";
  const diff = Math.round((now.getTime() - d.getTime()) / 1000);
  const future = diff < 0;
  const s = Math.abs(diff);
  const wrap = (v: string) => (future ? `in ${v}` : `${v} ago`);
  // A few seconds "in the future" is clock skew between the server and this browser.
  if (s < 45 || (future && s < 120)) return "just now";
  if (s < 3600) return wrap(`${Math.max(1, Math.round(s / 60))}m`);
  if (s < 86_400) return wrap(`${Math.round(s / 3600)}h`);
  if (s < 86_400 * 14) return wrap(`${Math.round(s / 86_400)}d`);
  return formatDate(iso);
}

/** Initials for an avatar: "Avery Chen" becomes "AC". */
export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

/** A decimal string or number from the API as a number; null when it is not one. */
export function toNumber(value: number | string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * US dollars, with enough precision to be honest about tiny AI costs:
 * $0 for zero, $0.0004 under a cent, $0.012 under a dollar, then $12.40 and $1,240.
 */
export function formatUsd(value: number | string | null | undefined): string {
  const n = toNumber(value);
  if (n == null) return "n/a";
  if (n === 0) return "$0";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs < 0.0001) return `${sign}<$0.0001`;
  if (abs < 0.01) return `${sign}$${trimZeros(abs.toFixed(4))}`;
  if (abs < 1) return `${sign}$${trimZeros(abs.toFixed(3))}`;
  if (abs < 1000) return `${sign}$${abs.toFixed(2)}`;
  return `${sign}$${intFmt.format(Math.round(abs))}`;
}

function trimZeros(fixed: string): string {
  return fixed.includes(".") ? fixed.replace(/0+$/, "").replace(/\.$/, "") : fixed;
}

/** 950, 12.4k, 3.1M tokens. */
export function formatTokens(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const abs = Math.abs(value);
  if (abs < 1000) return intFmt.format(value);
  if (abs < 1_000_000) return `${trim(value / 1000)}k`;
  return `${trim(value / 1_000_000)}M`;
}

/** A span in seconds as "45s", "4m", "1h 20m", "2d 3h". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "n/a";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) {
    const rest = m % 60;
    return rest ? `${h}h ${rest}m` : `${h}h`;
  }
  const d = Math.floor(h / 24);
  const restH = h % 24;
  return restH ? `${d}d ${restH}h` : `${d}d`;
}

/** Milliseconds as "320 ms" or "1.4 s". */
export function formatMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "n/a";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${trim(ms / 1000)} s`;
}

/** Minutes as the SLA editor shows them: "30 min", "4 h", "1 d 2 h". */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes)) return "n/a";
  return formatDuration(minutes * 60);
}

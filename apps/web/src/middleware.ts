import { NextResponse, type NextRequest } from "next/server";

const prod = process.env.NODE_ENV === "production";
const API_URL = (process.env.API_URL || process.env.API_INTERNAL_URL || "http://localhost:4830").replace(/\/+$/, "");
const WS_OVERRIDE = process.env.NEXT_PUBLIC_WS_URL || "";

/**
 * Next inlines its bootstrap scripts and styles, so those need 'unsafe-inline'; the dev
 * server also needs 'unsafe-eval' for fast refresh. Everything loads from and connects to
 * this origin. `frameAncestors` decides who may embed the page: nobody, except the widget
 * frame, which the inbox's allowed sites embed.
 */
export function contentSecurityPolicy(isProd = prod, frameAncestors = "'none'", wsOverride = WS_OVERRIDE): string {
  const connect = ["connect-src 'self'", ...(isProd ? [] : ["ws:"]), ...(wsOverride ? [wsOverride] : [])];
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    connect.join(" "),
    "frame-src 'self'",
    `frame-ancestors ${frameAncestors}`,
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

/** Agent pages; the widget, help center, portal and sign-in pages are public. */
const PROTECTED = ["/inbox", "/approvals", "/customers", "/knowledge", "/gaps", "/analytics", "/settings"];

export function needsSignIn(pathname: string): boolean {
  return PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * The frame-ancestors source list for an inbox's allowed sites. Only well formed origins
 * (scheme, host, optional port) or a lone "*" pass, so a stored value can never inject
 * another directive. The app's own origin ('self') may always embed it (help center).
 */
export function frameAncestorsFor(origins: unknown): string {
  const list = Array.isArray(origins) ? origins.filter((o): o is string => typeof o === "string") : [];
  if (list.includes("*")) return "'self' *";
  const valid = list.filter((o) => /^https?:\/\/[a-z0-9.-]+(:\d{1,5})?$/i.test(o));
  return ["'self'", ...valid].join(" ");
}

interface CacheEntry {
  value: string;
  at: number;
}

const FRAME_CACHE = new Map<string, CacheEntry>();
const FRAME_TTL_MS = 60_000;
const MAX_ENTRIES = 500;

/**
 * Ask the API which sites may embed this widget (GET /widget/{key}/frame-policy), cached
 * in memory for 60 seconds per key. When the API cannot be reached or the key is unknown,
 * only this origin may embed the frame: failing closed never exposes the widget to an
 * unlisted site.
 */
export async function widgetFrameAncestors(key: string, fetcher: typeof fetch = fetch, now = Date.now()): Promise<string> {
  if (!/^[A-Za-z0-9_-]{4,128}$/.test(key)) return "'self'";
  const hit = FRAME_CACHE.get(key);
  if (hit && now - hit.at < FRAME_TTL_MS) return hit.value;
  let value = "'self'";
  try {
    const res = await fetcher(`${API_URL}/api/v1/widget/${encodeURIComponent(key)}/frame-policy`, {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(2000),
    });
    if (res.ok) {
      const body = (await res.json()) as { frame_ancestors?: unknown };
      value = frameAncestorsFor(body.frame_ancestors);
    }
  } catch {
    value = "'self'";
  }
  if (FRAME_CACHE.size >= MAX_ENTRIES) FRAME_CACHE.clear();
  FRAME_CACHE.set(key, { value, at: now });
  return value;
}

/** Test hook: forget cached frame policies. */
export function clearFramePolicyCache() {
  FRAME_CACHE.clear();
}

/**
 * Sets the Content-Security-Policy on every page, and sends signed-out visitors of an
 * agent page straight to /login instead of flashing it. The cookie is only checked for
 * presence here; the API validates it on every call and the client redirects on 401.
 */
export async function middleware(req: NextRequest) {
  const hasSession = req.cookies.has("sd_session");
  const { pathname, search } = req.nextUrl;
  let res: NextResponse;
  if (!hasSession && needsSignIn(pathname)) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", `${pathname}${search}`);
    res = NextResponse.redirect(url);
  } else {
    res = NextResponse.next();
  }
  let ancestors = "'none'";
  if (pathname === "/widget/frame") {
    ancestors = await widgetFrameAncestors(req.nextUrl.searchParams.get("key") ?? "");
  }
  res.headers.set("Content-Security-Policy", contentSecurityPolicy(prod, ancestors));
  return res;
}

export const config = {
  // Everything except the proxied API surfaces, Next internals and static files.
  matcher: ["/((?!api/|ws/|healthz|readyz|docs|openapi\\.json|_next/|favicon|icon|widget\\.js|.*\\.(?:svg|png|jpg|ico|webp|txt|js|woff2?)$).*)"],
};

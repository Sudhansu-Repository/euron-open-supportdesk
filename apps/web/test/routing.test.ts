import { describe, expect, it, vi } from "vitest";

import { HOME, loginUrl, safeNext } from "@/lib/auth-redirect";
import { activeNavItem, groupContains, NAV, NAV_ITEMS, visibleTo } from "@/lib/nav";
import { isAgentPath } from "@/lib/providers";
import { clearFramePolicyCache, contentSecurityPolicy, frameAncestorsFor, needsSignIn, widgetFrameAncestors } from "@/middleware";

describe("sign-in redirects", () => {
  it("only follows same-origin paths and defaults to the inbox", () => {
    expect(HOME).toBe("/inbox");
    expect(safeNext("/inbox/abc?view=mine")).toBe("/inbox/abc?view=mine");
    expect(safeNext("https://evil.example")).toBe(HOME);
    expect(safeNext("//evil.example")).toBe(HOME);
    expect(safeNext("/\\evil.example")).toBe(HOME);
    expect(safeNext("/login")).toBe(HOME);
    expect(safeNext(null)).toBe(HOME);
  });
  it("keeps where the agent was", () => {
    expect(loginUrl("/analytics", "?days=7")).toBe("/login?next=%2Fanalytics%3Fdays%3D7");
    expect(loginUrl("/inbox", "", "expired")).toBe("/login?next=%2Finbox&reason=expired");
    expect(loginUrl("/")).toBe("/login");
    expect(loginUrl("/invite")).toBe("/login");
  });
  it("protects agent pages and leaves customer pages public", () => {
    for (const p of ["/inbox", "/inbox/x", "/approvals", "/customers/1", "/knowledge", "/gaps/2", "/analytics", "/settings/ai"]) expect(needsSignIn(p)).toBe(true);
    for (const p of ["/help/acme", "/help/acme/tickets", "/widget/frame", "/login", "/invite", "/inboxes"]) expect(needsSignIn(p)).toBe(false);
    expect(isAgentPath("/widget/frame")).toBe(false);
    expect(isAgentPath("/help/acme/tickets/1")).toBe(false);
    expect(isAgentPath("/inbox")).toBe(true);
  });
});

describe("content security policy", () => {
  it("lets nobody embed agent pages", () => {
    const csp = contentSecurityPolicy(true);
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).not.toContain("unsafe-eval");
    expect(contentSecurityPolicy(false)).toContain("unsafe-eval");
    expect(contentSecurityPolicy(true, "'self'", "ws://api:4830")).toContain("connect-src 'self' ws://api:4830");
  });
  it("builds frame-ancestors from the inbox's allowed sites, refusing anything odd", () => {
    expect(frameAncestorsFor(["https://a.example", "http://localhost:4815"])).toBe("'self' https://a.example http://localhost:4815");
    expect(frameAncestorsFor(["*"])).toBe("'self' *");
    expect(frameAncestorsFor(["https://a.example; script-src *", "javascript:x", 5])).toBe("'self'");
    expect(frameAncestorsFor(null)).toBe("'self'");
  });
  it("asks the API once per minute per key and fails closed", async () => {
    clearFramePolicyCache();
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ frame_ancestors: ["https://shop.example"] }), { status: 200 }));
    const t0 = 1_000_000;
    expect(await widgetFrameAncestors("pk_test123", fetcher, t0)).toBe("'self' https://shop.example");
    expect(await widgetFrameAncestors("pk_test123", fetcher, t0 + 30_000)).toBe("'self' https://shop.example");
    expect(fetcher).toHaveBeenCalledTimes(1);
    await widgetFrameAncestors("pk_test123", fetcher, t0 + 61_000);
    expect(fetcher).toHaveBeenCalledTimes(2);
    const down = vi.fn().mockRejectedValue(new Error("down"));
    expect(await widgetFrameAncestors("pk_other1", down, t0)).toBe("'self'");
    const missing = vi.fn().mockResolvedValue(new Response("{}", { status: 404 }));
    expect(await widgetFrameAncestors("pk_missing", missing, t0)).toBe("'self'");
    expect(await widgetFrameAncestors("bad key!", fetcher, t0)).toBe("'self'");
  });
});

describe("navigation", () => {
  const byHref = (href: string) => NAV_ITEMS.find((i) => i.href === href)!;
  it("shows settings to admins and owners only", () => {
    expect(visibleTo(byHref("/inbox"), "agent")).toBe(true);
    expect(visibleTo(byHref("/inbox"), null)).toBe(false);
    expect(visibleTo(byHref("/settings/ai"), "agent")).toBe(false);
    expect(visibleTo(byHref("/settings/ai"), "admin")).toBe(true);
    expect(visibleTo(byHref("/settings/ai"), "owner")).toBe(true);
  });
  it("highlights the deepest match and opens the settings group on a settings page", () => {
    expect(activeNavItem("/inbox/abc")?.href).toBe("/inbox");
    expect(activeNavItem("/knowledge/articles/1")?.href).toBe("/knowledge");
    expect(activeNavItem("/nowhere")).toBeUndefined();
    const settings = NAV.find((g) => g.collapsible)!;
    expect(groupContains(settings, "/settings/webhooks")).toBe(true);
    expect(groupContains(settings, "/inbox")).toBe(false);
  });
});

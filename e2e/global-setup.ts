import { request } from "@playwright/test";

import { CSRF, OWNER } from "./helpers";

/**
 * Sign in once as the demo owner and share the session cookie with every suite. Signing in
 * per test would meet the per-address sign-in limit on repeated runs, which is the limit
 * working as intended.
 */
export default async function globalSetup(): Promise<void> {
  const baseURL = process.env.WEB_URL || "http://localhost:4810";
  const ctx = await request.newContext({ baseURL, extraHTTPHeaders: CSRF });
  const resp = await ctx.post("/api/v1/auth/login", { data: OWNER });
  if (!resp.ok()) throw new Error(`demo sign-in failed (${resp.status()}): run make demo first`);
  await ctx.storageState({ path: ".auth/owner.json" });
  await ctx.dispose();
}

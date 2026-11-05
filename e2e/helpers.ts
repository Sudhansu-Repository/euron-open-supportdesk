import { type APIRequestContext, expect, type Page, request } from "@playwright/test";

export const BASE = process.env.WEB_URL || "http://localhost:4810";
export const API = process.env.API_URL || "http://localhost:4830";
export const DEMO_SITE = process.env.DEMO_SITE_URL || "http://localhost:4815";
export const MAILPIT = process.env.MAILPIT_URL || "http://localhost:4825";
export const PASSWORD = process.env.SD_DEMO_PASSWORD || "Demo-Pass-2026";
export const OWNER = { email: "maya@lumen.example", password: PASSWORD };
export const SLUG = "lumen";

/** Mutations through the API carry the CSRF header the web app sends. */
export const CSRF = { "x-supportdesk-csrf": "1" };

/** A per-run suffix so suites can run repeatedly against the same demo database. */
export const RUN = process.env.E2E_RUN || Date.now().toString(36).slice(-6);

/** Fail the test on any console error the page reports. */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

async function retrying(fn: () => Promise<import("@playwright/test").APIResponse>) {
  for (let i = 0; i < 10; i++) {
    const resp = await fn();
    if (resp.status() !== 429) return resp;
    await new Promise((r) => setTimeout(r, Number(resp.headers()["retry-after"] ?? "5") * 1000));
  }
  return fn();
}

/** An API client signed in as someone (waits out the sign-in limit if needed). */
export async function apiAs(email: string, password = PASSWORD): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: BASE, extraHTTPHeaders: CSRF });
  const resp = await retrying(() => ctx.post("/api/v1/auth/login", { data: { email, password } }));
  expect(resp.status(), await resp.text()).toBe(200);
  return ctx;
}

/** JSON from the API, asserting success. */
export async function call<T = unknown>(ctx: APIRequestContext, method: string, path: string, data?: unknown): Promise<T> {
  const resp = await retrying(() => ctx.fetch(path, { method, data }));
  expect(resp.status(), `${method} ${path}: ${await resp.text()}`).toBeLessThan(300);
  return (resp.status() === 204 ? null : await resp.json()) as T;
}

/** Poll until ``fn`` returns something truthy. */
export async function eventually<T>(fn: () => Promise<T | null | undefined | false>, timeoutMs = 60_000): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let last: unknown = null;
  while (Date.now() < deadline) {
    last = await fn();
    if (last) return last as T;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`condition never held (last: ${JSON.stringify(last)?.slice(0, 200)})`);
}

/** The newest Mailpit message to an address, once it arrives. */
export async function mailTo(address: string, after = 0): Promise<{ Text: string; HTML: string; Headers?: Record<string, string[]>; ID: string }> {
  const ctx = await request.newContext({ baseURL: MAILPIT });
  try {
    return await eventually(async () => {
      const found = await (await ctx.get(`/api/v1/search?query=${encodeURIComponent(`to:${address}`)}`)).json();
      const msg = (found.messages ?? []).find((m: { Created: string }) => Date.parse(m.Created) >= after);
      if (!msg) return null;
      const full = await (await ctx.get(`/api/v1/message/${msg.ID}`)).json();
      const headers = await (await ctx.get(`/api/v1/message/${msg.ID}/headers`)).json();
      return { ...full, Headers: headers };
    });
  } finally {
    await ctx.dispose();
  }
}

/** The demo company's widget key. */
export async function widgetKey(): Promise<string> {
  const ctx = await request.newContext({ baseURL: BASE });
  const help = await (await ctx.get(`/api/v1/help/${SLUG}`)).json();
  await ctx.dispose();
  return help.widget_key as string;
}

/** Upload a knowledge file through the API and wait until it is indexed. */
export async function uploadKnowledge(ctx: APIRequestContext, name: string, body: string, type: string): Promise<string> {
  const resp = await ctx.post("/api/v1/knowledge/sources/upload", {
    multipart: { file: { name, mimeType: type, buffer: Buffer.from(body) } },
  });
  expect(resp.status(), await resp.text()).toBe(201);
  const id = (await resp.json()).id as string;
  await eventually(async () => {
    const sources = await call<{ id: string; status: string }[]>(ctx, "GET", "/api/v1/knowledge/sources");
    const s = sources.find((x) => x.id === id);
    return s && s.status === "ready";
  });
  return id;
}

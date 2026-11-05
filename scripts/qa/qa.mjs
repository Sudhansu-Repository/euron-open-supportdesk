/**
 * Browser QA (make qa): signs in through the real form as each role, visits every page in
 * light and dark at desktop and phone width, saves screenshots, and fails on console
 * errors, failed or 4xx/5xx requests, broken images, error states, empty pages with no
 * explanation, and horizontal overflow.
 *
 *   make qa
 *   QA_BASE=http://localhost:4810 QA_OUT=./output node qa.mjs
 *   QA_PAGES=/inbox,/analytics QA_THEMES=dark QA_SIZES=desktop node qa.mjs
 *
 * Needs the seeded stack (make up && make demo). Uses Puppeteer's bundled Chromium; set
 * CHROME_PATH to use a local browser instead.
 */
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer";

const BASE = process.env.QA_BASE ?? "http://localhost:4810";
const DEMO_SITE = process.env.QA_DEMO_SITE ?? "http://localhost:4815";
const MAILPIT = process.env.QA_MAILPIT ?? "http://localhost:4825";
const OUT = process.env.QA_OUT ?? path.resolve("output");
const PASSWORD = process.env.SD_DEMO_PASSWORD ?? process.env.QA_PASSWORD ?? "Demo-Pass-2026";
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;
const SLUG = process.env.QA_SLUG ?? "lumen";

const OWNER = "maya@lumen.example";
const AGENT = "sofia@lumen.example";
const CUSTOMER_EMAIL = "qa.customer@example.com";

// Pages per role. Placeholders are resolved from the seeded data once.
const ROLE_PAGES = {
  anonymous: [
    "/login",
    "/signup",
    `/help/${SLUG}`,
    `/help/${SLUG}/articles/:article`,
    `/help/${SLUG}/signin`,
    "/widget/frame?key=:widgetKey",
    `${DEMO_SITE}/`,
  ],
  owner: [
    "/inbox",
    "/inbox?view=unassigned",
    "/inbox?view=sla",
    "/inbox/:ticket",
    "/inbox/:escalated",
    "/approvals",
    "/customers",
    "/customers/:customer",
    "/knowledge",
    "/knowledge/articles/new",
    "/knowledge/articles/:articleId",
    "/gaps",
    "/gaps/:gap",
    "/analytics",
    "/settings",
    "/settings/organisation",
    "/settings/team",
    "/settings/inboxes",
    "/settings/ai",
    "/settings/policy",
    "/settings/budgets",
    "/settings/prices",
    "/settings/sla",
    "/settings/macros",
    "/settings/api-keys",
    "/settings/webhooks",
    "/settings/audit",
  ],
  agent: ["/inbox", "/inbox?view=mine", "/inbox/:escalated", "/approvals", "/customers", "/knowledge", "/analytics"],
  customer: [`/help/${SLUG}/tickets`, `/help/${SLUG}/tickets/new`, `/help/${SLUG}/tickets/:portalTicket`],
};
const ONLY = process.env.QA_PAGES ? new Set(process.env.QA_PAGES.split(",")) : null;
const ROLES = (process.env.QA_ROLES ?? "anonymous,owner,agent,customer").split(",");
const THEMES = (process.env.QA_THEMES ?? "light,dark").split(",");
const SIZES = {
  desktop: { width: 1440, height: 900 },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};
const SIZE_KEYS = (process.env.QA_SIZES ?? "desktop,phone").split(",");
const FULL = process.env.QA_FULL !== "0";

function slug(p) {
  return p.replace(/^https?:\/\/[^/]+/, "site").replace(/^\//, "").replace(/[/:?=&]/g, "-") || "home";
}

async function api(token, method, url, body) {
  const resp = await fetch(`${BASE}${url}`, {
    method,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", "x-supportdesk-csrf": "1" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`${method} ${url}: ${resp.status} ${await resp.text()}`);
  return resp.status === 204 ? null : resp.json();
}

async function token(email) {
  const resp = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-supportdesk-csrf": "1" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  if (!resp.ok) throw new Error(`sign-in for ${email} failed (${resp.status}): run make demo first`);
  return (await resp.json()).session_token;
}

/** Ids of seeded records for the parameterised pages. */
async function resolveIds() {
  const t = await token(OWNER);
  const tickets = await api(t, "GET", "/api/v1/tickets?limit=50");
  const resolved = await api(t, "GET", "/api/v1/tickets?view=resolved&limit=50");
  const escalated = await api(t, "GET", "/api/v1/tickets?view=escalated&limit=5");
  const customers = await api(t, "GET", "/api/v1/customers?limit=5");
  const articles = await api(t, "GET", "/api/v1/knowledge/articles");
  const gaps = await api(t, "GET", "/api/v1/gaps");
  const help = await (await fetch(`${BASE}/api/v1/help/${SLUG}`)).json();
  const published = articles.find((a) => a.status === "published");
  const withAi = resolved.items.find((x) => x.ai_resolved) ?? tickets.items[0];
  return {
    ticket: withAi.id,
    escalated: escalated.items[0]?.id ?? tickets.items[0].id,
    customer: customers[0].id,
    article: published.slug,
    articleId: published.id,
    gap: gaps[0]?.id ?? "none",
    widgetKey: help.widget_key,
  };
}

let portalSession = null;

/** A real portal session: ask for a magic link, read it from Mailpit, open it. Done once:
 * links are rate limited per address, so later browser contexts reuse the session. */
async function portalSignIn(page, ids) {
  if (portalSession) {
    await page.goto(`${BASE}/help/${SLUG}`, { waitUntil: "networkidle2" });
    await page.evaluate((entries) => {
      for (const [k, v] of entries) localStorage.setItem(k, v);
    }, portalSession);
    return;
  }
  const requested = Date.now() - 2000;
  await fetch(`${BASE}/api/v1/portal/${SLUG}/link`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: CUSTOMER_EMAIL }),
  });
  let link = null;
  for (let i = 0; i < 30 && !link; i++) {
    const found = await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${CUSTOMER_EMAIL}`)}`)).json();
    // Only a link sent for this request: an older one has been used already.
    const fresh = (found.messages ?? []).find((m) => Date.parse(m.Created) >= requested);
    if (fresh) {
      const msg = await (await fetch(`${MAILPIT}/api/v1/message/${fresh.ID}`)).json();
      const m = /(https?:\/\/\S+\/signin\?token=[A-Za-z0-9_-]+)/.exec(`${msg.Text} ${msg.HTML}`);
      if (m) link = m[1];
    }
    if (!link) await new Promise((r) => setTimeout(r, 1000));
  }
  if (!link) throw new Error("the portal sign-in email never reached Mailpit");
  await page.goto(link, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));
  portalSession = await page.evaluate(() =>
    Object.keys(localStorage).filter((k) => k.includes("portal")).map((k) => [k, localStorage.getItem(k)]),
  );
  if (!ids.portalTicket) {
    const portalToken = await page.evaluate(() => {
      for (const k of Object.keys(localStorage)) if (k.includes("portal")) return localStorage.getItem(k);
      return null;
    });
    const raw = portalToken?.startsWith("{") ? JSON.parse(portalToken).token : portalToken;
    const headers = { authorization: `Bearer ${raw}`, "content-type": "application/json" };
    let list = await (await fetch(`${BASE}/api/v1/portal/${SLUG}/tickets`, { headers })).json();
    if (!Array.isArray(list) || !list.length) {
      await fetch(`${BASE}/api/v1/portal/${SLUG}/tickets`, {
        method: "POST",
        headers,
        body: JSON.stringify({ subject: "Bridge light is orange", body: "My Lumen Bridge shows an orange light. What does it mean?" }),
      });
      list = await (await fetch(`${BASE}/api/v1/portal/${SLUG}/tickets`, { headers })).json();
    }
    ids.portalTicket = Array.isArray(list) && list.length ? list[0].id : "none";
  }
}

async function signInForm(page, email) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.type("#email", email);
  await page.type("#password", PASSWORD);
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2" }), page.click("button[type=submit]")]);
}

function watch(page, sink) {
  page.on("console", (m) => {
    if (m.type() === "error") sink.push(m.text());
  });
  page.on("pageerror", (e) => sink.push(`pageerror: ${e.message}`));
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText ?? "";
    if (!err.includes("ERR_ABORTED")) sink.push(`requestfailed ${r.url()} ${err}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400) sink.push(`HTTP ${r.status()} ${r.url()}`);
  });
}

async function inspect(page) {
  return page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth - window.innerWidth;
    const broken = [...document.images].filter((img) => img.complete && img.naturalWidth === 0).map((img) => img.src);
    const errorStates = [...document.querySelectorAll("[data-qa='error-state']")].map((el) => el.textContent?.slice(0, 80) ?? "");
    const main = document.querySelector("main") ?? document.body;
    const text = (main.textContent ?? "").replace(/\s+/g, " ").trim();
    return { overflow, broken, errorStates, empty: text.length < 40 };
  });
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const ids = await resolveIds();
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const findings = [];
  let visited = 0;

  for (const role of ROLES) {
    const pages = ROLE_PAGES[role].filter((p) => !ONLY || ONLY.has(p));
    if (!pages.length) continue;
    for (const theme of THEMES) {
      for (const sizeKey of SIZE_KEYS) {
        const ctx = await browser.createBrowserContext();
        const page = await ctx.newPage();
        await page.setViewport(SIZES[sizeKey]);
        await page.evaluateOnNewDocument((t) => {
          try {
            localStorage.setItem("theme", t);
          } catch {}
        }, theme);
        const errors = [];
        watch(page, errors);
        if (role === "owner") await signInForm(page, OWNER);
        if (role === "agent") await signInForm(page, AGENT);
        if (role === "customer") await portalSignIn(page, ids);
        for (const p of pages) {
          const url = p.replace(/(?<=[/=]):(\w+)/g, (_, k) => ids[k] ?? k);
          errors.length = 0;
          await page.goto(url.startsWith("http") ? url : `${BASE}${url}`, { waitUntil: "networkidle2", timeout: 60_000 });
          await new Promise((r) => setTimeout(r, 1200));
          const found = await inspect(page);
          const file = path.join(OUT, `${role}-${sizeKey}-${theme}-${slug(p)}.png`);
          await page.screenshot({ path: file, fullPage: FULL });
          const issues = [...errors];
          if (found.overflow > 1) issues.push(`horizontal overflow ${found.overflow}px`);
          for (const src of found.broken) issues.push(`broken image ${src}`);
          for (const text of found.errorStates) issues.push(`error state: ${text}`);
          if (found.empty) issues.push("page is empty with no explanation");
          if (issues.length) findings.push({ role, page: p, theme, size: sizeKey, issues });
          visited += 1;
          console.log(`${issues.length ? "WARN" : "ok  "} ${role} ${sizeKey} ${theme} ${p}${issues.length ? `: ${issues.join(" | ")}` : ""}`);
        }
        await ctx.close();
      }
    }
  }
  await browser.close();
  console.log(`\n${visited} page views, ${findings.length} with problems. Screenshots in ${OUT}`);
  if (findings.length) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

/**
 * Curated README screenshots and tour frames from the seeded stack (real data only).
 *
 *   make up && make demo
 *   make screenshots                 (or: cd scripts/qa && node screenshots.mjs)
 *   scripts/qa/make-tour.sh          (stitches the frames into docs/assets/tour.gif)
 *
 * The widget captures are real: a visitor on the demo customer site (another origin) asks
 * a question, the worker answers from the knowledge base with the bundled mock model, the
 * visitor asks for a person and an agent replies from the inbox.
 *
 * Writes docs/assets/screenshots/NN-name.png and scripts/qa/output/tour/NN.png.
 */
import { mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.QA_BASE ?? "http://localhost:4810";
const DEMO_SITE = process.env.QA_DEMO_SITE ?? "http://localhost:4815";
const PASSWORD = process.env.SD_DEMO_PASSWORD ?? process.env.QA_PASSWORD ?? "Demo-Pass-2026";
const SHOTS = path.resolve(HERE, "../../docs/assets/screenshots");
const TOUR = path.resolve(HERE, "output/tour");
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1 };
const PHONE = { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 };
const OWNER = "maya@lumen.example";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let tourIndex = 0;

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
  if (!resp.ok) throw new Error(`sign-in failed (${resp.status}): run make demo first`);
  return (await resp.json()).session_token;
}

async function newPage(browser, viewport, theme = "light") {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport(viewport);
  await page.evaluateOnNewDocument((t) => {
    try {
      localStorage.setItem("theme", t);
    } catch {}
  }, theme);
  return page;
}

async function signIn(page, email) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await page.type("#email", email);
  await page.type("#password", PASSWORD);
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2" }), page.click("button[type=submit]")]);
}

async function open(page, url, settle = 1500) {
  await page.goto(url.startsWith("http") ? url : `${BASE}${url}`, { waitUntil: "networkidle2", timeout: 60_000 });
  await sleep(settle);
}

async function shot(page, name, { tour = true, full = false } = {}) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: full });
  if (tour) {
    tourIndex += 1;
    await page.screenshot({ path: path.join(TOUR, `${String(tourIndex).padStart(2, "0")}.png`) });
  }
  console.log(`saved ${name}`);
}

/** Type into the widget frame on the demo site and wait for the reply. */
async function widgetAsk(frame, text, expect) {
  await frame.type('textarea[aria-label="Your message"]', text);
  await frame.click('button[aria-label="Send"]');
  await frame.waitForFunction((needle) => document.body.innerText.includes(needle), { timeout: 60_000 }, expect);
  await sleep(800);
}

async function main() {
  await mkdir(SHOTS, { recursive: true });
  await rm(TOUR, { recursive: true, force: true });
  await mkdir(TOUR, { recursive: true });
  const owner = await token(OWNER);
  const escalated = (await api(owner, "GET", "/api/v1/tickets?view=escalated&limit=10")).items;
  const breached = escalated.find((t) => t.sla_state === "breached") ?? escalated[0];
  const resolved = (await api(owner, "GET", "/api/v1/tickets?view=resolved&limit=50")).items.find((t) => t.ai_resolved);
  const gaps = await api(owner, "GET", "/api/v1/gaps");
  const help = await (await fetch(`${BASE}/api/v1/help/lumen`)).json();

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  try {
    // 1. A visitor on the customer's own website asks; the AI answers with its source.
    const site = await newPage(browser, DESKTOP);
    await open(site, DEMO_SITE);
    await site.click('button[aria-label="Open support chat"]');
    await sleep(1500);
    const frameHandle = await site.waitForSelector('iframe[title="Support chat"]');
    const frame = await frameHandle.contentFrame();
    await frame.waitForSelector('textarea[aria-label="Your message"]');
    await widgetAsk(frame, "My bulb won't pair, what should I try?", "2.4 GHz");
    await shot(site, "01-widget-cited-answer");

    // 2. Agent inbox: an escalation with the AI's summary and reason.
    const agent = await newPage(browser, DESKTOP);
    await signIn(agent, OWNER);
    await open(agent, `/inbox/${breached.id}`);
    await shot(agent, "02-inbox-handoff");

    // 3. A conversation the AI resolved: citations and the decision panel.
    await open(agent, `/inbox/${resolved.id}`);
    await shot(agent, "03-ai-resolved");

    // 4. Approvals: sensitive answers held for a person.
    await open(agent, "/approvals");
    await shot(agent, "04-approvals");

    // 5. Knowledge sources and the playground.
    await open(agent, "/knowledge");
    await shot(agent, "05-knowledge");
    await agent.evaluate(() => [...document.querySelectorAll('[role="tab"]')].find((t) => /test/i.test(t.textContent ?? ""))?.click());
    await sleep(600);
    await agent.type('[aria-label="Test question"]', "Can I return an unused starter kit?");
    await agent.keyboard.press("Enter");
    await agent.waitForFunction(() => /30 days/.test(document.body.innerText), { timeout: 60_000 });
    await sleep(1000);
    await shot(agent, "06-playground");

    // 7. Knowledge gaps.
    await open(agent, `/gaps/${gaps[0].id}`);
    await shot(agent, "07-knowledge-gap");

    // 8. Analytics with the cost per AI resolution (wait for the chart to draw).
    await open(agent, "/analytics", 4000);
    await shot(agent, "08-analytics");

    // 9. Policy and escalation; 10. the widget designer and snippet.
    await open(agent, "/settings/policy");
    await shot(agent, "09-policy");
    await open(agent, "/settings/inboxes");
    await shot(agent, "10-widget-designer");

    // 11. The public help center.
    const visitor = await newPage(browser, DESKTOP);
    await open(visitor, `/help/${help.slug}`);
    await shot(visitor, "11-help-center");

    // 12. Dark mode inbox.
    const dark = await newPage(browser, DESKTOP, "dark");
    await signIn(dark, OWNER);
    await open(dark, `/inbox/${breached.id}`);
    await shot(dark, "12-dark-inbox", { tour: false });

    // 13. Phone: the widget on the customer site; 14. the agent inbox on a phone.
    const phone = await newPage(browser, PHONE);
    await open(phone, DEMO_SITE);
    await phone.click('button[aria-label="Open support chat"]');
    await sleep(1500);
    const phoneFrame = await (await phone.waitForSelector('iframe[title="Support chat"]')).contentFrame();
    await phoneFrame.waitForSelector('textarea[aria-label="Your message"]');
    await widgetAsk(phoneFrame, "How long does shipping take?", "business days");
    await shot(phone, "13-phone-widget", { tour: false });
    const phoneAgent = await newPage(browser, PHONE);
    await signIn(phoneAgent, OWNER);
    await open(phoneAgent, "/inbox");
    await shot(phoneAgent, "14-phone-inbox", { tour: false });
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

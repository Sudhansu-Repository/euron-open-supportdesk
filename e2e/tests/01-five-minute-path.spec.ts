import { expect, request, test } from "@playwright/test";

import { CSRF, DEMO_SITE, OWNER, RUN, apiAs, call, eventually, watchConsole } from "../helpers";

/**
 * AC13, the five-minute path: upload a document in the app, ask about it in the widget on
 * a different website, get a cited answer, ask for a person, reply as the agent from the
 * inbox, and see the reply arrive in the widget live.
 */
test("knowledge upload to cited widget answer to agent handoff", async ({ page, browser }) => {
  const errors = watchConsole(page);
  const fact = `The Lumen Aurora ${RUN} lamp runs for 14 hours on a full charge.`;

  // 1. Upload a Markdown file through the Knowledge screen.
  await page.goto("/knowledge");
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: `aurora-${RUN}.md`,
    mimeType: "text/markdown",
    buffer: Buffer.from(`# Aurora ${RUN} battery\n\n${fact} It charges fully in 3 hours over USB-C.\n`),
  });
  const owner = await apiAs(OWNER.email);
  await eventually(async () => {
    const sources = await call<{ title: string; status: string }[]>(owner, "GET", "/api/v1/knowledge/sources");
    return sources.find((s) => s.title.includes(RUN) && s.status === "ready");
  }, 120_000);

  // 2. A customer on another website asks about it.
  const customer = await browser.newPage();
  await customer.goto(DEMO_SITE);
  await customer.getByRole("button", { name: "Open support chat" }).click();
  const chat = customer.frameLocator('iframe[title="Support chat"]');
  await chat.getByLabel("Your message").fill(`How many hours does the Aurora ${RUN} lamp run on a full charge?`);
  await chat.getByLabel("Send").click();
  await expect(chat.getByText(/14 hours/).last()).toBeVisible({ timeout: 60_000 });
  await expect(chat.getByText(new RegExp(`Aurora ${RUN} battery`)).first()).toBeVisible();

  // 3. They ask for a person.
  await chat.getByRole("button", { name: "Talk to a person" }).click();
  await expect(chat.getByText(/connecting you with a teammate/i)).toBeVisible({ timeout: 30_000 });

  // 4. The agent finds the conversation in the inbox and replies.
  const found = await eventually(async () => {
    const list = await call<{ items: { id: string; handled_by: string }[] }>(
      owner, "GET", `/api/v1/tickets?q=${encodeURIComponent(`Aurora ${RUN}`)}`,
    );
    return list.items.find((t) => t.handled_by === "human");
  });
  await page.goto(`/inbox/${found.id}`);
  await page.getByLabel(/^Reply to /).fill(`Hi! The Aurora ${RUN} also has a power saving mode.`);
  await page.getByRole("button", { name: "Send reply" }).click();

  // 5. The reply reaches the widget without a reload.
  await expect(chat.getByText(/power saving mode/)).toBeVisible({ timeout: 30_000 });

  // 6. The agent resolves it.
  await page.getByRole("button", { name: /Resolve/ }).first().click();
  await eventually(async () => {
    const t = await call<{ status: string }>(owner, "GET", `/api/v1/tickets/${found.id}`);
    return t.status === "resolved";
  });
  expect(errors, errors.join("\n")).toEqual([]);
  await customer.close();
  await owner.dispose();
});

test("the API refuses an embed from a website that is not allowed", async () => {
  const ctx = await request.newContext({ extraHTTPHeaders: CSRF });
  const key = (await (await ctx.get(`${process.env.WEB_URL || "http://localhost:4810"}/api/v1/help/lumen`)).json()).widget_key;
  const refused = await ctx.post(`${process.env.WEB_URL || "http://localhost:4810"}/api/v1/widget/${key}/session`, {
    data: { parent_origin: "https://evil.example" },
    headers: { origin: process.env.WEB_URL || "http://localhost:4810" },
  });
  expect(refused.status()).toBe(403);
  const policy = await (await ctx.get(`${process.env.WEB_URL || "http://localhost:4810"}/widget/frame?key=${key}`)).headers();
  expect(policy["content-security-policy"]).toContain("frame-ancestors");
  expect(policy["content-security-policy"]).toContain("http://localhost:4815");
  expect(policy["content-security-policy"]).not.toContain("evil.example");
  await ctx.dispose();
});

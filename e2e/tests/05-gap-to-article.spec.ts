import { expect, request, test } from "@playwright/test";

import { BASE, OWNER, RUN, apiAs, call, eventually, widgetKey } from "../helpers";

async function ask(key: string, question: string): Promise<{ author_type: string; body: string; ticket_id: string }> {
  const ctx = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { origin: BASE } });
  const token = (await (await ctx.post(`/api/v1/widget/${key}/session`, { data: {} })).json()).token;
  const headers = { authorization: `Bearer ${token}` };
  const conv = await (await ctx.post("/api/v1/widget/messages", { data: { body: question }, headers })).json();
  const reply = await eventually(async () => {
    const c = await (await ctx.get(`/api/v1/widget/tickets/${conv.ticket_id}`, { headers })).json();
    const last = c.messages[c.messages.length - 1];
    return last.author_type !== "customer" ? { ...last, ticket_id: conv.ticket_id } : null;
  });
  await ctx.dispose();
  return reply;
}

/** AC7: unanswered questions become a gap; an article drafted from it closes the gap and
 * the AI answers the next customer. */
test("knowledge gap to published article to AI answer", async ({ page }) => {
  test.setTimeout(300_000);
  const key = await widgetKey();
  // Every content word is unique to this run, so earlier runs' articles cannot answer it.
  const topic = `Garmin${RUN} Wear${RUN}`;
  // A topic the knowledge base does not cover at all, asked twice in different words.
  const first = await ask(key, `Do you offer ${topic}?`);
  expect(first.author_type).toBe("system");
  await ask(key, `Is ${topic} available?`);
  // An agent answers one of them: that reply becomes the article draft.
  const owner = await apiAs(OWNER.email);
  await call(owner, "POST", `/api/v1/tickets/${first.ticket_id}/messages`, {
    body: `Yes: ${topic} works with Lumen.`,
  });
  // Similar questions join one gap (possibly an older one with the same topic), so find
  // the gap by the questions it holds, not by its title.
  const gap = await eventually(async () => {
    const gaps = await call<{ id: string }[]>(owner, "GET", "/api/v1/gaps");
    for (const g of gaps) {
      const detail = await call<{ id: string; questions: { question: string }[] }>(owner, "GET", `/api/v1/gaps/${g.id}`);
      if (detail.questions.some((q) => q.question.includes(topic))) return detail;
    }
    return null;
  }, 180_000);

  await page.goto(`/gaps/${gap.id}`);
  await page.getByRole("button", { name: /Draft article/ }).or(page.getByRole("link", { name: /Draft article/ })).first().click();
  await expect(page).toHaveURL(/\/knowledge\/articles\/new\?gap=/);
  const body = page.getByLabel("Article body in Markdown");
  await expect(body).toHaveValue(new RegExp(`Garmin${RUN}`), { timeout: 60_000 });
  await page.locator("#a-title").fill(`${topic}`);
  await body.fill(`Yes: ${topic} works with Lumen.`);
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText(/gap is closed/i)).toBeVisible({ timeout: 30_000 });

  const answered = await eventually(async () => {
    const reply = await ask(key, `Do you offer ${topic}?`);
    return reply.author_type === "ai" ? reply : null;
  }, 120_000);
  expect(answered.body).toContain(`Garmin${RUN}`);
  await owner.dispose();
});

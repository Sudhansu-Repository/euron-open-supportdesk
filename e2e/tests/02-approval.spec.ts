import { expect, test } from "@playwright/test";

import { DEMO_SITE, OWNER, RUN, apiAs, call, eventually } from "../helpers";

/** AC3: a refund request is answered only after an agent approves the AI's draft. */
test("a sensitive answer waits for approval and is sent when approved", async ({ page, browser }) => {
  const customer = await browser.newPage();
  await customer.goto(DEMO_SITE);
  await customer.getByRole("button", { name: "Open support chat" }).click();
  const chat = customer.frameLocator('iframe[title="Support chat"]');
  await chat.getByLabel("Your message").fill(`I want a refund for my unused starter kit ${RUN}, what is your return policy?`);
  await chat.getByLabel("Send").click();
  await expect(chat.getByText(/teammate is checking this/i)).toBeVisible({ timeout: 60_000 });
  await expect(chat.getByText(/30 days of delivery/)).toHaveCount(0);

  const owner = await apiAs(OWNER.email);
  const pending = await eventually(async () => {
    const list = await call<{ items: { id: string; subject: string }[] }>(owner, "GET", "/api/v1/tickets?view=approvals");
    return list.items.find((t) => t.subject.includes(RUN));
  });
  await page.goto(`/inbox/${pending.id}`);
  await page.getByRole("button", { name: "Approve and send" }).first().click();
  await expect(chat.getByText(/30 days of delivery/)).toBeVisible({ timeout: 30_000 });
  const after = await call<{ pending_approval: boolean }>(owner, "GET", `/api/v1/tickets/${pending.id}`);
  expect(after.pending_approval).toBe(false);
  await customer.close();
  await owner.dispose();
});

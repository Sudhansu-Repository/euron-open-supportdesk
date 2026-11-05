import { expect, test } from "@playwright/test";

import { RUN, SLUG, mailTo } from "../helpers";

/** AC9, portal: a customer signs in with a magic link, opens a ticket and sees it listed. */
test.use({ storageState: { cookies: [], origins: [] } });

test("magic link sign-in, new ticket, ticket list", async ({ page }) => {
  const email = `portal.${RUN}@example.com`;
  const started = Date.now();
  await page.goto(`/help/${SLUG}/signin`);
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: /link/i }).click();
  await expect(page.getByText(/on its way|check your inbox/i)).toBeVisible();
  const mail = await mailTo(email, started - 1000);
  const link = /(https?:\/\/\S+\/signin\?token=[A-Za-z0-9_-]+)/.exec(mail.Text)![1];
  await page.goto(link);
  await expect(page).toHaveURL(new RegExp(`/help/${SLUG}/tickets`), { timeout: 30_000 });
  await page.getByRole("button", { name: "New ticket" }).or(page.getByRole("link", { name: "New ticket" })).first().click();
  await page.getByLabel("Subject").fill(`Bridge light ${RUN}`);
  await page.getByLabel("Details").fill("My Lumen Bridge shows an orange light. What does it mean?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(`Bridge light ${RUN}`).first()).toBeVisible({ timeout: 30_000 });
  await page.goto(`/help/${SLUG}/tickets`);
  await expect(page.getByText(`Bridge light ${RUN}`)).toBeVisible();
});

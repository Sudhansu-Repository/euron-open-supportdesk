import { expect, request, test } from "@playwright/test";

import { API, OWNER, RUN, apiAs, call, eventually, mailTo } from "../helpers";

/** AC9, email: an inbound email opens a conversation, the agent's reply leaves by SMTP
 * with threading headers, and the customer's reply joins the same conversation. */
test("email in, reply out with threading, reply back into the same ticket", async ({ page }) => {
  const owner = await apiAs(OWNER.email);
  const inboxes = await call<{ id: string; channel: string }[]>(owner, "GET", "/api/v1/inboxes");
  const email = inboxes.find((i) => i.channel === "email")!;
  const { secret } = await call<{ secret: string }>(owner, "PATCH", `/api/v1/inboxes/${email.id}`, { rotate_inbound_token: true });
  const sender = `pat.${RUN}@example.com`;
  const raw = (subject: string, body: string, to: string, id: string, inReplyTo?: string) =>
    [`From: Pat ${RUN} <${sender}>`, `To: ${to}`, `Subject: ${subject}`, `Message-ID: <${id}@mail.example>`,
     ...(inReplyTo ? [`In-Reply-To: ${inReplyTo}`, `References: ${inReplyTo}`] : []),
     "Content-Type: text/plain; charset=utf-8", "", body].join("\r\n");
  const api = await request.newContext({ baseURL: API });
  const first = await api.post(`/api/v1/channels/email/inbound/${secret}`, {
    headers: { "content-type": "message/rfc822" },
    data: raw(`Partnership ${RUN}`, "We run cafes and want to talk about lighting.", "support@lumen.example", `a${RUN}`),
  });
  expect(first.status(), await first.text()).toBe(200);
  const { ticket_id } = await first.json();

  const started = Date.now();
  await page.goto(`/inbox/${ticket_id}`);
  await expect(page.getByText("We run cafes and want to talk about lighting.").first()).toBeVisible();
  await page.getByLabel(/^Reply to /).fill(`Thanks Pat! Our business team will call you ${RUN}.`);
  await page.getByRole("button", { name: "Send reply" }).click();

  const mail = await mailTo(sender, started - 1000);
  expect(mail.Text).toContain("Our business team will call you");
  const headers = mail.Headers ?? {};
  expect(headers["In-Reply-To"]?.[0]).toBe(`<a${RUN}@mail.example>`);
  const replyTo = headers["Reply-To"]?.[0] ?? "";
  expect(replyTo).toContain("+");

  const back = await api.post(`/api/v1/channels/email/inbound/${secret}`, {
    headers: { "content-type": "message/rfc822" },
    data: raw(`Re: Partnership ${RUN}`, "Great, Tuesday works.\n\nOn Mon, Support wrote:\n> Thanks Pat!", replyTo, `b${RUN}`),
  });
  expect((await back.json()).ticket_id).toBe(ticket_id);
  await expect(page.getByText("Great, Tuesday works.").first()).toBeVisible({ timeout: 30_000 });
  await eventually(async () => (await call<{ status: string }>(owner, "GET", `/api/v1/tickets/${ticket_id}`)).status === "open");
  await api.dispose();
  await owner.dispose();
});

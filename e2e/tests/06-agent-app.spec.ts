import { expect, test } from "@playwright/test";

import { watchConsole } from "../helpers";

/** The agent app's main screens render real data without errors. */
const SCREENS: [string, RegExp][] = [
  ["/inbox", /Unassigned|Mine/],
  ["/approvals", /approv/i],
  ["/customers", /Customers/],
  ["/knowledge", /Frequently asked questions/],
  ["/gaps", /HomeKit/],
  ["/analytics", /AI resolution/i],
  ["/settings/policy", /approval/i],
  ["/settings/inboxes", /widget\.js/],
  ["/settings/ai", /Test connection/i],
];

for (const [path, marker] of SCREENS) {
  test(`renders ${path}`, async ({ page }) => {
    const errors = watchConsole(page);
    await page.goto(path);
    await expect(page.getByText(marker).first()).toBeVisible({ timeout: 30_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });
}

test("the playground shows the decision and the passages", async ({ page }) => {
  await page.goto("/knowledge");
  await page.getByRole("tab", { name: /Test a question|Playground/i }).click();
  await page.getByLabel("Test question").fill("How long does shipping take?");
  await page.getByLabel("Test question").press("Enter");
  await expect(page.getByText(/3 to 5 business days/).first()).toBeVisible({ timeout: 60_000 });
});

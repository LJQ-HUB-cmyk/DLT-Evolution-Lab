import { expect, test } from "@playwright/test";

import { installApiMock } from "./api-mock";

test.describe("mobile smoke", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMock(page);
  });

  test("drawer opens and sticky meta visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("sticky-meta")).toBeVisible();
    await page.getByRole("button", { name: "历史开奖" }).click();
    await expect(page.getByTestId("history-pane")).toBeVisible();
  });
});

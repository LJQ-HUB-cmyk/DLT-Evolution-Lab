import { expect, test } from "@playwright/test";

import { installApiMock } from "./api-mock";

test.describe("desktop smoke", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMock(page);
  });

  test("home loads, key panels visible, predict once", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("app-root")).toBeVisible();
    await expect(page.getByTestId("model-meta-panel")).toBeVisible();
    await expect(page.getByTestId("history-pane")).toBeVisible();
    await page.getByTestId("btn-experiment").click();
    await expect(page.getByText(/run_1/)).toBeVisible({ timeout: 15_000 });
  });
});

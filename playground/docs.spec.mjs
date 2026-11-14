import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("documentation and playground share one website without a browser runtime", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const remote = [];
  page.on("request", (request) => {
    if (request.url().startsWith("https://")) remote.push(request.url());
  });
  await page.goto("/");
  await page.locator(".site-nav").getByRole("link", { name: "Documentation", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Documentation");
  const menu = page.getByRole("navigation", { name: "Documentation pages" });
  await menu.getByText("Browse documentation", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await menu.getByRole("link", { name: "Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/config\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Configuration");
  await page.goto("docs/config/#require-values-in-selected-files");
  await expect(page.locator("#require-values-in-selected-files")).toBeInViewport();
  await page.getByRole("link", { name: "required-field-missing", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/rules\/#required-field-missing$/);
  await expect(page.locator("#required-field-missing")).toBeInViewport();

  for (const colorScheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("docs/config/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`docs-${colorScheme}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "light" });
  await page.screenshot({ path: testInfo.outputPath("docs-desktop.png"), fullPage: true });
  await page.locator(".site-nav").getByRole("link", { name: "Playground", exact: true }).click();
  await expect(page.getByRole("heading", { name: "citesync", exact: true })).toBeVisible();
  expect(remote).toEqual([]);
  await context.close();
});

test("format tables and nested decision guides retain links on narrow screens", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  for (const guide of ["config", "formats", "output", "decisions", "decisions/0002-vendored-mapping"]) {
    await page.goto(`docs/${guide}/`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(
      (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations,
    ).toEqual([]);
  }
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://simonvanlierde.com/citesync/docs/decisions/0002-vendored-mapping/",
  );
  await expect(page.getByRole("link", { name: "View this page on GitHub" })).toHaveAttribute(
    "href",
    "https://github.com/simonvanlierde/citesync/blob/main/docs/decisions/0002-vendored-mapping.md",
  );
});

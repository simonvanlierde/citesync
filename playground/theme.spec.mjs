import { expect, test } from "@playwright/test";

test("theme choice overrides the system and follows navigation between both surfaces", async ({
  browser,
}, testInfo) => {
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ colorScheme });
    const page = await context.newPage();
    await page.goto("/docs/");
    const footer = page.locator("footer");
    await expect(footer.getByRole("link", { name: "Simon van Lierde", exact: true })).toBeVisible();
    await footer.screenshot({ path: testInfo.outputPath(`docs-footer-${colorScheme}.png`) });
    const chosen = colorScheme === "light" ? "dark" : "light";
    await expect(page.locator("html")).toHaveAttribute("data-theme", colorScheme);
    const header = page.locator("header");
    const toggle = header.getByRole("button", { name: `Switch to ${chosen} theme` });
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("html")).toHaveAttribute("data-theme", chosen);
    await expect(page.getByRole("button", { name: `Switch to ${colorScheme} theme` })).toBeVisible();
    await expect(header.locator(`.theme-${chosen === "dark" ? "sun" : "moon"}`)).toBeVisible();
    await expect(page.locator("body")).toHaveAttribute("data-md-color-scheme", chosen === "dark" ? "slate" : "default");
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", chosen);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", chosen);
    await expect(page.locator("html")).toHaveCSS("color-scheme", chosen);
    await page.getByRole("button", { name: `Switch to ${colorScheme} theme` }).click();
    await expect(page.locator("html")).toHaveCSS("color-scheme", colorScheme);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page
      .locator("footer")
      .screenshot({ path: testInfo.outputPath(`playground-footer-${colorScheme}-mobile.png`) });
    await page.goto("/docs/");
    await expect(page.locator("html")).toHaveCSS("color-scheme", colorScheme);
    await expect(page.locator("body")).toHaveAttribute(
      "data-md-color-scheme",
      colorScheme === "dark" ? "slate" : "default",
    );
    await context.close();
  }
});

test("theme follows system changes until chosen and tolerates blocked storage", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "light" });
  await context.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("Storage blocked");
    };
    Storage.prototype.setItem = () => {
      throw new Error("Storage blocked");
    };
  });
  const page = await context.newPage();
  await page.goto("/docs/");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveAttribute("data-md-color-scheme", "slate");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveCSS("color-scheme", "light");
  await expect(page.locator("body")).toHaveAttribute("data-md-color-scheme", "default");
  await context.close();
});

test("without JavaScript both surfaces retain the system theme", async ({ browser }) => {
  for (const colorScheme of ["light", "dark"]) {
    const context = await browser.newContext({ javaScriptEnabled: false, colorScheme });
    const page = await context.newPage();
    for (const route of ["/", "/docs/"]) {
      await page.goto(route);
      await expect(page.locator("html")).toHaveCSS("color-scheme", colorScheme);
      await expect(page.locator(".theme-toggle")).toBeHidden();
    }
    await context.close();
  }
});

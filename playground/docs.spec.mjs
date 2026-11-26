import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.use({ trace: "retain-on-failure" });

test("the playground and docs share one website and retain native anchors", async ({
  browser,
  browserName,
}, testInfo) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const remote = [];
  page.on("request", (request) => {
    if (request.url().startsWith("https://")) remote.push(request.url());
  });
  await page.goto("/");
  await page.locator(".site-nav").getByRole("link", { name: "Documentation", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Documentation");

  await page.setViewportSize({ width: 400, height: 900 });
  const guides = page.locator(".docs-fallback");
  const disclosure = guides.getByText("Browse documentation", { exact: true });
  await disclosure.focus();
  await page.keyboard.press("Enter");
  await guides.getByRole("link", { name: "Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/config\/$/);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("docs/config/#require-values-in-selected-files");
  await expect(page.locator("#require-values-in-selected-files")).toBeInViewport();

  let delayedStylesheet = false;
  if (browserName === "chromium") {
    // A stylesheet arriving after fragment navigation reproduced the historical failure.
    await page.route("**/docs/assets/stylesheets/modern/main.*.css", async (route) => {
      delayedStylesheet = true;
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });
  }
  await page.locator("article").getByRole("link", { name: "required-field-missing", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/rules\/#required-field-missing$/);
  await page.waitForLoadState("load");
  if (browserName === "chromium") expect(delayedStylesheet).toBe(true);
  try {
    await expect.poll(() => page.evaluate(() => document.fonts.status)).toBe("loaded");
    await expect(page.locator("#required-field-missing")).toBeInViewport();
  } catch (error) {
    try {
      const geometry = await page.evaluate(() => ({
        url: location.href,
        scrollY,
        viewport: { width: innerWidth, height: innerHeight },
        documentHeight: document.documentElement.scrollHeight,
        target: document.getElementById("required-field-missing")?.getBoundingClientRect().toJSON() ?? null,
        fonts: document.fonts.status,
        readyState: document.readyState,
      }));
      await testInfo.attach("anchor-geometry", {
        body: JSON.stringify(geometry, null, 2),
        contentType: "application/json",
      });
    } catch {
      // Preserve the viewport assertion if the page closes before collecting diagnostics.
    }
    throw error;
  }

  await page.getByText("Browse documentation", { exact: true }).click();
  await page.locator(".docs-fallback").getByRole("link", { name: "Playground", exact: true }).click();
  await expect(page.getByRole("heading", { name: "citesync", exact: true })).toBeVisible();
  expect(remote).toEqual([]);
  await context.close();
});

test("documentation search stays local and opens the matching section", async ({ page, baseURL }) => {
  const externalRequests = [];
  const policyViolations = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(baseURL)) externalRequests.push(request.url());
  });
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) {
      policyViolations.push(message.text());
    }
  });
  await page.goto("docs/");
  await page.getByRole("button", { name: /^Search(?: Ctrl|$)/ }).click();
  const search = page.getByRole("combobox", { name: "Search" });
  await search.fill("required-field-missing");
  const result = page.locator('dialog a[href*="#required-field-missing"]').first();
  await expect(result).toBeVisible();
  await result.click();
  await expect(page).toHaveURL(/\/docs\/rules\/#required-field-missing$/);
  await expect(page.locator("#required-field-missing")).toBeInViewport();
  await page.getByRole("button", { name: /^Search(?: Ctrl|$)/ }).click();
  await search.fill("uv tool install");
  await expect(page.locator('dialog a[href*="getting-started"]').first()).toBeVisible();
  expect(externalRequests).toEqual([]);
  expect(policyViolations).toEqual([]);
});

test("docs remain readable and accessible at phone and desktop widths", async ({ page }, testInfo) => {
  for (const width of [400, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const colorScheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme });
      await page.goto("docs/config/");
      await expect(page.locator("body")).toHaveAttribute(
        "data-md-color-scheme",
        colorScheme === "dark" ? "slate" : "default",
      );
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Configuration");
      await expect(page.getByRole("button", { name: /^Search(?: Ctrl|$)/ })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      expect(
        (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations,
      ).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`docs-${width}-${colorScheme}.png`) });
    }
  }
});

test("the project footer and canonical docs URLs survive the migration", async ({ page }) => {
  for (const route of ["/", "docs/accessibility/"]) {
    await page.goto(route);
    const footer = page.locator("footer");
    await expect(footer).toContainText("citesync");
    await expect(footer).toContainText("2026");
    await expect(footer.getByRole("link", { name: "Simon van Lierde", exact: true })).toHaveAttribute(
      "href",
      "https://simonvanlierde.com/",
    );
    await expect(footer.getByRole("link", { name: "DOI: 10.5281/zenodo.23779706", exact: true })).toHaveAttribute(
      "href",
      "https://doi.org/10.5281/zenodo.23779706",
    );
    await expect(footer.getByRole("link", { name: "Apache-2.0 licence", exact: true })).toBeVisible();
    await footer.getByRole("link", { name: "Accessibility", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Accessibility");
  }
  await page.goto("docs/decisions/0002-vendored-mapping/");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://simonvanlierde.com/citesync/docs/decisions/0002-vendored-mapping/",
  );
});

test("mobile reference tables preserve identifiers and scroll with the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 900 });
  await page.goto("docs/formats/");
  const region = page.getByRole("region", { name: /table \d+, scrolls sideways/i }).first();
  await expect(region).toBeVisible();
  await region.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("installation commands copy exactly and report blocked clipboard access", async ({ page }) => {
  await page.addInitScript(() => {
    window.copied = null;
    window.blocked = false;
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async (text) => {
          if (window.blocked) throw new Error("clipboard denied");
          window.copied = text;
        },
      },
    });
  });
  await page.goto("docs/getting-started/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Getting started");
  await expect(page.locator("article pre").first()).toContainText("uv tool install citesync");
  const copy = page.getByRole("button", { name: "Copy to clipboard", exact: true }).first();
  await copy.focus();
  await expect(copy).toBeFocused();
  const target = await copy.boundingBox();
  expect(target.width).toBeGreaterThanOrEqual(44);
  expect(target.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press("Enter");
  await expect(page.locator(".docs-copy-status")).toContainText("Copied to clipboard.");
  const expected = await page.locator("article pre code").first().textContent();
  expect(await page.evaluate(() => window.copied)).toBe(expected);
  await expect(copy).toBeFocused();
  await page.evaluate(() => {
    window.blocked = true;
  });
  await page.keyboard.press("Enter");
  await expect(page.locator(".docs-copy-status")).toContainText("Select the code and copy it manually.");
  await expect(page.locator("article pre code").first()).toBeVisible();
});

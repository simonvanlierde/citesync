import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("both footers identify the project and link its accessibility statement", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/", "/docs/accessibility/"]) {
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
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const surface = route === "/" ? "playground" : "documentation";
      await footer.screenshot({ path: testInfo.outputPath(`${surface}-footer-${width}.png`) });
      await footer.getByRole("link", { name: "Accessibility", exact: true }).click();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Accessibility");
    }
  }
  await context.close();
});

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
  for (const guide of [
    "accessibility",
    "config",
    "formats",
    "output",
    "decisions",
    "decisions/0002-vendored-mapping",
  ]) {
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
});

test("documentation navigation distinguishes commands and identifies the current section", async ({ page }) => {
  await page.goto("docs/check/");
  const menu = page.getByRole("navigation", { name: "Documentation pages" });
  for (const command of ["check", "init", "write"]) {
    await expect(menu.getByRole("link", { name: `How citesync ${command} works`, exact: true })).toBeVisible();
  }
  await expect(menu.locator('[aria-current="page"]')).toHaveText("How citesync check works");
  await page.goto("docs/decisions/0002-vendored-mapping/");
  await expect(menu.locator('[aria-current="location"]')).toHaveText("Design decisions");
});

test("mobile reference tables preserve filenames and scroll with the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("docs/formats/");
  const table = page.getByRole("table").first();
  const lines = await table
    .locator("tbody tr")
    .first()
    .locator("td")
    .first()
    .evaluate((cell) => {
      const range = document.createRange();
      range.selectNodeContents(cell);
      return range.getClientRects().length;
    });
  expect(lines).toBe(1);
  const region = page.getByRole("region", { name: "Scrollable table" }).first();
  await region.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("full-text documentation search keeps reading on the website", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("docs/");
  const search = page.getByRole("searchbox", { name: "Search documentation" });
  await search.fill("required-field-missing");
  const results = page.getByRole("list", { name: "Search results" });
  await expect(results).toBeVisible();
  await expect(results.getByRole("link").first()).toHaveAttribute("href", /\/docs\/.+#/);
  await expect(page.getByRole("status")).toContainText("matching section");
  await search.fill("zzzz-no-such-documentation");
  await expect(page.getByRole("status")).toContainText("No matching sections");
  await search.press("Escape");
  await expect(search).toHaveValue("");
  await expect(results).toBeHidden();
  await search.fill("uv tool install");
  await expect(results.getByRole("link", { name: "Getting started", exact: true })).toBeVisible();
  await search.press("Tab");
  const installation = results.getByRole("link", { name: "Getting started", exact: true });
  if (await results.evaluate((element) => element === document.activeElement)) await page.keyboard.press("Tab");
  await expect(installation).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/docs\/getting-started\/#getting-started$/);
  await expect(page.locator("#getting-started")).toBeInViewport();
  expect(requests.some((url) => url.includes("required-field-missing") || url.includes("zzzz-no-such"))).toBe(false);
  const localGuides = page.locator('article a[href*="github.com/simonvanlierde/citesync/blob/main/"][href*=".md"]');
  await expect(localGuides).toHaveCount(0);
});

test("documentation search recovers after an index download failure", async ({ page }) => {
  await page.route("**/docs/search-index.json", (route) => route.abort());
  await page.goto("docs/config/");
  await expect(page.getByRole("status")).toContainText("Search could not load");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Configuration");
  await page.getByRole("searchbox").fill("dataset");
  await page.unroute("**/docs/search-index.json");
  await page.getByRole("button", { name: "Retry search" }).click();
  await expect(page.getByRole("list", { name: "Search results" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry search" })).toBeHidden();
});

test("documentation search and reading layout adapt to phones and desktops", async ({ page }, testInfo) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const colorScheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme });
      await page.goto("docs/config/");
      await expect(page.getByRole("searchbox", { name: "Search documentation" })).toBeVisible();
      const menu = page.getByRole("navigation", { name: "Documentation pages" });
      if (width < 801) {
        await expect(menu.getByRole("link", { name: "Getting started", exact: true })).toBeHidden();
        await menu.getByText("Browse documentation", { exact: true }).click();
        await expect(menu.getByRole("link", { name: "Getting started", exact: true })).toBeVisible();
        await menu.getByText("Browse documentation", { exact: true }).click();
      } else {
        await expect(menu.getByRole("link", { name: "Getting started", exact: true })).toBeVisible();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`docs-${width}-${colorScheme}.png`), fullPage: true });
      await page.getByRole("searchbox").fill("dataset licence");
      await expect(page.getByRole("list", { name: "Search results" })).toBeVisible();
      await expect(page.locator("#docs-search-more")).toContainText("Scroll the results to read all");
      await expect(page.locator("#docs-search-more")).toBeVisible();
      const reorderedWords = await page.locator("#docs-search-results a").evaluateAll((links) =>
        links.flatMap((link) => {
          const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT);
          const words = [];
          while (walker.nextNode()) {
            const node = walker.currentNode;
            for (const match of node.textContent.matchAll(/\S+/g)) {
              const range = document.createRange();
              range.setStart(node, match.index);
              range.setEnd(node, match.index + match[0].length);
              words.push({ text: match[0], rect: range.getBoundingClientRect() });
            }
          }
          return words.slice(1).flatMap((word, index) => {
            const previous = words[index];
            const sameLine = Math.abs(word.rect.top - previous.rect.top) <= 2;
            return word.rect.top < previous.rect.top - 2 || (sameLine && word.rect.left < previous.rect.right - 2)
              ? [`${previous.text} → ${word.text} in ${link.textContent}`]
              : [];
          });
        }),
      );
      expect(reorderedWords).toEqual([]);

      expect(
        (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations,
      ).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`search-${width}-${colorScheme}.png`) });
    }
  }
});

test("documentation makes no remote requests and installation starts with commands", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const remote = [];
  page.on("request", (request) => {
    if (request.url().startsWith("https://")) remote.push(request.url());
  });
  for (const route of ["getting-started", "repository", "playground", "contributing"]) {
    await page.goto(`docs/${route}/`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (route === "getting-started") {
      await expect(page.getByRole("heading", { name: "Getting started", exact: true })).toBeVisible();
      await expect(page.locator("article pre").first()).toContainText("uv tool install citesync");
      await expect(page.locator("article pre").first()).toBeInViewport();
    }
  }
  expect(remote).toEqual([]);
  await context.close();
});

test("search highlighting renders literal query text safely", async ({ page }) => {
  await page.route("**/docs/search-index.json", (route) =>
    route.fulfill({
      json: [
        {
          title: "Guide",
          heading: "Literal <img>",
          text: "Use <img src=x onerror=alert(1)> and [fields] safely.",
          url: "config/#configuration",
        },
      ],
    }),
  );
  await page.goto("docs/");
  await page.getByRole("searchbox").fill("<img [fields]");
  const results = page.getByRole("list", { name: "Search results" });
  await expect(results.locator("p mark")).toHaveText(["<img", "[fields]"]);
  await expect(results.locator("img")).toHaveCount(0);
});

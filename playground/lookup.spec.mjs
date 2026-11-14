import fs from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const pinned = JSON.parse(fs.readFileSync(new URL("../src/citesync/mapping-local.json", import.meta.url)));
const source = fs.readFileSync(new URL("../src/citesync/MAPPING_SOURCE", import.meta.url), "utf8");

test("field lookup uses the pinned mapping without waiting for Python", async ({ page }, testInfo) => {
  await page.route("https://cdn.jsdelivr.net/**", (route) => route.abort());
  await page.goto("/");
  await page.getByText("Field lookup", { exact: true }).focus();
  await page.keyboard.press("Enter");
  const cards = page.locator("#lookup-results section");
  await expect(cards).toHaveCount(6);
  await expect(cards.locator("h3")).toHaveText([
    "CITATION.cff",
    "codemeta.json",
    ".zenodo.json",
    "pyproject.toml",
    "Cargo.toml",
    "package.json",
  ]);
  const mapping = await page.evaluate(async () => {
    const script = document.querySelector('script[src$="main.mjs"]');
    return (await fetch(new URL("lookup.json", script.src))).json();
  });
  expect(mapping.rows).toEqual(pinned.rows);
  expect(source).toContain(`tag ${mapping.tag}\n`);
  expect(source).toContain(`commit ${mapping.commit}\n`);
  await expect(page.locator("#lookup-source")).toHaveAttribute(
    "href",
    `https://github.com/simonvanlierde/codemeta-drift/tree/${mapping.commit}`,
  );

  const search = page.getByRole("searchbox", { name: "Find a field" });
  await search.fill("  TITLE ");
  await expect(page.locator("#lookup-status")).toHaveText("1 matching field");
  await expect(cards.locator("dt")).toHaveText(Array(6).fill("name"));
  await expect(cards.first().locator("code")).toHaveText("title");
  await expect(cards.nth(3).locator("code")).toHaveText("project.name");
  await search.fill("doi");
  await expect(cards.locator("dt")).toHaveText(Array(6).fill("identifier"));
  await expect(cards.nth(4)).toContainText("Not represented in this mapping");
  await expect(search).toBeFocused();
  await search.fill("nothing-matches");
  await expect(cards).toHaveCount(0);
  await expect(page.locator("#lookup-status")).toContainText("No matching fields");
  await search.fill("author.givenName");
  await expect(cards).toHaveCount(6);

  for (const colorScheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(
      (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations,
    ).toEqual([]);
    await page.locator("#field-lookup").screenshot({ path: testInfo.outputPath(`lookup-${colorScheme}.png`) });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "light" });
  await page.locator("#field-lookup").screenshot({ path: testInfo.outputPath("lookup-desktop.png") });
});

test("field lookup retains a typed search when loading fails and retries", async ({ page }) => {
  await page.route("https://cdn.jsdelivr.net/**", (route) => route.abort());
  let attempts = 0;
  await page.route("**/lookup.json", (route) => {
    attempts++;
    return attempts === 1 ? route.fulfill({ status: 503, body: "unavailable" }) : route.continue();
  });
  await page.goto("/");
  await page.getByText("Field lookup", { exact: true }).click();
  await page.getByRole("searchbox", { name: "Find a field" }).fill("license");
  await expect(page.locator("#lookup-status")).toContainText("could not load");
  await page.getByRole("button", { name: "Retry field lookup" }).click();
  await expect(page.locator("#lookup-results dt")).toHaveText(Array(6).fill("license"));
  await expect(page.getByRole("searchbox", { name: "Find a field" })).toHaveValue("license");
  await expect(page.getByRole("button", { name: "Retry field lookup" })).toBeHidden();
});

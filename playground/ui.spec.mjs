import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const syntaxMessage = /line|expected|parse/i;
async function accessible(page) {
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
}

test("automatic detection, live name corrections, exports, form and parse recovery", async ({ page }) => {
  const errors = [];
  const downloads = [];
  page.on("download", (download) => downloads.push(download));
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await accessible(page);
  await expect(page.getByRole("button", { name: "Generate citation files" })).toHaveCount(0);
  await page.getByRole("button", { name: "Try an example" }).click();
  await expect(page.locator("#name-review")).toBeVisible({ timeout: 90000 });
  await expect(page.locator("#detected-format")).toHaveText("Detected pyproject.toml");
  expect(downloads).toHaveLength(0);
  await expect(page.locator("#runtime")).toHaveText("Finishing converter setup… You can keep editing.");
  await expect(page.locator("#runtime")).toBeHidden();
  await expect(page.locator('#output-file option[value="CITATION.cff"]')).toHaveText("CITATION.cff — GitHub citation");
  await expect(page.locator('#output-file option[value=".zenodo.json"]')).toHaveText(".zenodo.json — Zenodo deposit");
  await expect(page.locator("#copy")).toBeEnabled();
  await page.locator("#review-0-family").fill("van Leeuwenhoek");
  await expect(page.locator("#output")).toContainText("family-names: van Leeuwenhoek");
  await expect(page.locator("#review-0-family")).toBeFocused();
  await expect(page.locator("#zip")).toBeEnabled();
  await page.locator("#output-file").selectOption("citation.bib");
  await expect(page.locator("#output")).toContainText("@misc{software,");
  await page.locator("#output-file").selectOption("citation.csl.json");
  await expect(page.locator("#output")).toContainText('"type": "software"');
  await page.locator("#output-file").selectOption("codemeta.json");
  await expect(page.locator("#output")).toContainText('"familyName": "van Leeuwenhoek"');
  await page.locator("#output-file").selectOption("CITATION.cff");
  const download = page.waitForEvent("download");
  await page.locator("#zip").click();
  expect((await download).suggestedFilename()).toBe("citesync-files.zip");
  await page.locator("#input").fill("[project\n");
  await expect(page.locator("#zip")).toBeDisabled();
  await page.locator("#source-format").focus();
  await page.locator("#source-format").selectOption("pyproject.toml");
  await expect(page.locator("#message")).toContainText(syntaxMessage);
  await expect(page.locator("#input")).toHaveValue("[project\n");
  await expect(page.locator("#source-format")).toBeFocused();
  await accessible(page);
  await page.getByRole("tab", { name: "Enter details" }).click();
  await page.locator("#title").fill("lensgrind");
  await page.locator('#authors [data-part="given"]').fill("Marie");
  await page.locator('#authors [data-part="family"]').fill("Skłodowska-Curie");
  await expect(page.locator("#zip")).toBeEnabled();
  await expect(page.locator('#authors [data-part="family"]')).toBeFocused();
  await expect(page.locator("#name-review")).toBeHidden();
  await expect(page.locator("#output")).toContainText("Skłodowska-Curie");
  for (const [width, scheme] of [
    [1440, "light"],
    [390, "light"],
    [320, "light"],
    [1440, "dark"],
  ]) {
    await page.setViewportSize({ height: 1000, width });
    await page.emulateMedia({ colorScheme: scheme });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await accessible(page);
    await page.screenshot({ fullPage: true, path: `test-results/ready-${width}-${scheme}.png` });
  }
  await page.locator("#output-file").selectOption("package.json");
  await expect(page.locator("#output")).toContainText('"private": true');
  await expect(page.locator("#template-warning")).toContainText("Metadata only");
  await accessible(page);
  await page.setViewportSize({ width: 320, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await accessible(page);
  await page.screenshot({ path: "test-results/package-templates-mobile.png", fullPage: true });
  await expect(page.locator("#zip")).toBeHidden();
  const template = page.waitForEvent("download");
  await page.locator("#download").click();
  expect((await template).suggestedFilename()).toBe("package.json");
  await page.getByRole("tab", { name: "Use a file", exact: true }).click();
  await expect(page.locator("#file-panel")).toBeVisible();
  await page.locator("#file-picker").setInputFiles({
    name: "metadata.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(JSON.stringify({ name: "lensgrind", author: "Marie Skłodowska-Curie" })),
  });
  await expect(page.locator("#detected-format")).toHaveText("Detected package.json");
  await expect(page.locator("#name-review")).toBeVisible();
  expect(errors).toEqual([]);
});

test("background runtime failure preserves a draft and retries without a generate button", async ({ page }) => {
  await page.route("https://cdn.jsdelivr.net/**", (route) => route.abort());
  await page.goto("/");
  await page.getByRole("button", { name: "Try an example" }).click();
  const draft = await page.locator("#input").inputValue();
  await expect(page.locator("#retry")).toBeVisible();
  await expect(page.locator("#message")).toContainText("could not load");
  await expect(page.locator("#input")).toHaveValue(draft);
  await accessible(page);
  await page.unroute("https://cdn.jsdelivr.net/**");
  await page.locator("#retry").click();
  await expect(page.locator("#name-review")).toBeVisible({ timeout: 90000 });
});

test("a newer draft wins while the runtime loads; ambiguous input needs an override", async ({ page }) => {
  const requests = [];
  page.on("request", (request) =>
    requests.push({ url: request.url(), method: request.method(), body: request.postData() }),
  );
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/runtime.json", async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto("/");
  await page.locator("#input").fill(JSON.stringify({ name: "old-project", author: "Antonie van Leeuwenhoek" }));
  await expect(page.locator("#message")).toContainText("Preparing");
  await page.locator("#input").fill(JSON.stringify({ name: "latest-project", author: "Marie Skłodowska-Curie" }));
  release();
  await expect(page.locator("#output")).toContainText("latest-project", { timeout: 90000 });
  await expect(page.locator("#output")).not.toContainText("old-project");
  expect(
    requests.every(
      (request) => request.method === "GET" && request.body === null && !request.url.includes("latest-project"),
    ),
  ).toBe(true);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  await page.locator("#input").fill('[project]\nname="one"\n[package]\nname="two"');
  await expect(page.locator("#detected-format")).toContainText("Could be");
  await expect(page.locator("#zip")).toBeDisabled();
});

test("examples follow the selected format and name editing stays optional", async ({ page }) => {
  await page.goto("/");
  for (const filename of [
    "CITATION.cff",
    "codemeta.json",
    ".zenodo.json",
    "pyproject.toml",
    "Cargo.toml",
    "package.json",
  ]) {
    await page.locator("#source-format").selectOption(filename);
    await page.locator("#example").click();
    await expect(page.locator("#source-format")).toHaveValue(filename);
    await expect(page.locator("#output")).toContainText("lensgrind", { timeout: 90000 });
    await expect(page.locator("#status")).not.toContainText("Updating");
    await expect(page.locator("#message")).toBeEmpty();
    if (filename === ".zenodo.json") {
      await page.locator("#output-file").selectOption(filename);
      await expect(page.locator("#output")).toContainText('"upload_type": "software"');
      await page.locator("#output-file").selectOption("CITATION.cff");
    }
  }
  await expect(page.locator("#copy")).toBeEnabled();
  await page.locator("#name-review summary").click();
  await expect(page.locator("#review-0-given")).toBeHidden();
  await page.locator("#name-review summary").click();
  await page.locator("#review-0-family").fill("van Leeuwenhoek");
  await expect(page.locator("#output")).toContainText("van Leeuwenhoek");
  await expect(page.locator("#copy")).toBeEnabled();
  await page.locator("#output-file").selectOption("package.json");
  await expect(page.locator("#output")).toContainText('"private": true');
  await expect(page.locator("#template-warning")).toBeVisible();
  await page.locator("#output-file").selectOption("CITATION.cff");
  await expect(page.locator("#template-warning")).toBeHidden();
  await page.getByRole("tab", { name: "Pre-commit", exact: true }).click();
  await expect(page.locator("#snippet-hook")).toContainText("id: citesync");
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#snippet-ci")).toBeVisible();
  await expect(page.getByRole("link", { name: "Docs", exact: true })).toHaveCount(1);
  await expect(page.getByRole("link", { name: "Author & portfolio", exact: true })).toHaveCount(0);
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await page.setViewportSize({ width: 320, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await accessible(page);
});

test("example switching preserves edits; name review and optional fields do not block copying", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page.locator("#example").click();
  await page.locator("#source-format").selectOption("Cargo.toml");
  await expect(page.locator("#input")).toHaveValue(/\[package\]/);
  await page.locator("#input").fill('[package]\nname="my-draft"\nauthors=["Marie Curie"]');
  await page.locator("#source-format").selectOption("pyproject.toml");
  await expect(page.locator("#input")).toHaveValue('[package]\nname="my-draft"\nauthors=["Marie Curie"]');
  await page.locator("#source-format").selectOption("Cargo.toml");
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  await expect(page.locator("#name-review")).not.toHaveAttribute("open", "");
  await expect(page.locator("#notes")).not.toContainText("no file holds a value");
  await page.locator("#copy").click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("my-draft");
  await page.getByRole("button", { name: "Copy code", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("uvx citesync init");
  await page.locator("#output-file").selectOption("package.json");
  await expect(page.locator("#zip")).toBeHidden();
  await expect(page.locator("#download")).toBeEnabled();
  await accessible(page);
});

test("invalid input clears progress", async ({ page }) => {
  await page.goto("/");
  await page.locator("#example").click();
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  await page.locator("#source-format").selectOption("pyproject.toml");
  await page.locator("#input").fill("[project\n");
  await expect(page.locator("#message")).toContainText(syntaxMessage);
  await expect(page.locator("#status")).not.toContainText("Updating");
  await page.locator("#source-format").selectOption("auto");
  await page.locator("#input").fill("unrecognised metadata");
  await expect(page.locator("#detected-format")).toContainText("not recognised");
  await expect(page.locator("#status")).not.toContainText("Updating");
});

test("selecting an output keeps the preview and copy action in place", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Enter details" }).click();
  await page.locator("#title").fill("lensgrind");
  await page.locator('#authors [data-part="family"]').fill("Curie");
  await expect(page.locator("#copy")).toBeEnabled();
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.locator("#output-file").selectOption("CITATION.cff");
    const preview = await page.locator("#output").boundingBox();
    const copy = await page.locator("#copy").boundingBox();
    for (const filename of ["citation.bib", "package.json", "Cargo.toml", "pyproject.toml", "codemeta.json"]) {
      await page.locator("#output-file").selectOption(filename);
      const next = await page.locator("#output").boundingBox();
      expect(next.y).toBeCloseTo(preview.y, 0);
      expect(next.height).toBeCloseTo(preview.height, 0);
      expect((await page.locator("#copy").boundingBox()).y).toBeCloseTo(copy.y, 0);
    }
    await accessible(page);
  }
  await page.locator('#authors [data-part="family"]').fill("");
  await expect(page.locator("#message")).toContainText("family name");
  await expect(page.locator("#status")).not.toContainText("Updating");
});

test("search metadata and project information are present without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(baseURL);
  await expect(page).toHaveTitle("citesync — software citation file generator");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://simonvanlierde.com/citesync/");
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
    "content",
    "https://simonvanlierde.com/citesync/",
  );
  await expect(page.locator('meta[name="description"]')).toHaveAttribute(
    "content",
    /CITATION.cff, CodeMeta, BibTeX and CSL-JSON/,
  );
  await expect(page.getByRole("heading", { name: "citesync", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Use citesync in your repository" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Docs", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Author & portfolio", exact: true })).toHaveCount(0);
  await context.close();
});

test("project metadata transfers between entry methods without replacing an unchanged file", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Enter details" }).click();
  await page.locator("#title").fill("draft optics");
  await page.getByRole("tab", { name: "Use a file", exact: true }).click();
  await expect(page.locator("#file-panel")).toBeVisible();
  await expect(page.locator("#input")).toHaveValue(/draft optics/, { timeout: 90000 });
  const source = JSON.stringify({
    "@context": "https://w3id.org/codemeta/3.0",
    "@type": "SoftwareSourceCode",
    name: "lensgrind",
    version: "1.4.0",
    author: [
      { "@type": "Person", givenName: "Marie", familyName: "Curie", "@id": "https://orcid.org/0000-0002-1825-0097" },
    ],
    custom: { keep: true },
  });
  await page.locator("#input").fill(source);
  await page.getByRole("tab", { name: "Enter details" }).click();
  await expect(page.locator("#title")).toHaveValue("lensgrind");
  await expect(page.locator('#authors [data-part="family"]')).toHaveValue("Curie");
  await page.getByRole("tab", { name: "Use a file", exact: true }).click();
  await expect(page.locator("#file-panel")).toBeVisible();
  await expect(page.locator("#input")).toHaveValue(source);
  await page.getByRole("tab", { name: "Enter details" }).click();
  await page.locator("#title").fill("new optics");
  await page.getByRole("tab", { name: "Use a file", exact: true }).click();
  await expect(page.locator("#file-panel")).toBeVisible();
  const changed = JSON.parse(await page.locator("#input").inputValue());
  expect(changed.name).toBe("new optics");
  expect(changed.custom).toEqual({ keep: true });
  expect(changed.author[0]["@id"]).toBe("https://orcid.org/0000-0002-1825-0097");
});

test("form validation uses the note colours and technical hints stay visible", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Enter details" }).click();
  await page.locator("#title").fill("lensgrind");
  await expect(page.locator("#message")).toHaveAttribute("data-notice", "true");
  expect(await page.locator("#message").evaluate((element) => getComputedStyle(element).backgroundColor)).toBe(
    "rgb(248, 238, 219)",
  );
  await page.locator('#authors [data-part="family"]').fill("Curie");
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  await page.locator("#output-file").selectOption(".zenodo.json");
  await expect(page.locator("#output")).toContainText('"upload_type": "software"');
  await expect(page.locator("#notes")).not.toContainText("requires an existing");
  await page.getByText("Version, licence and repository", { exact: true }).click();
  await page.getByText("Which version format?", { exact: true }).click();
  await expect(page.getByRole("link", { name: "PEP 440", exact: true })).toBeVisible();
  await page.getByText("Find a licence identifier", { exact: true }).click();
  await expect(page.getByRole("link", { name: "SPDX licence list", exact: true })).toBeVisible();
  await page.locator("#licence").fill("Apache-2.0");
  await expect(page.locator("#licence-hint")).toBeVisible();
  await accessible(page);
});

test("an unchanged uploaded citation file keeps its line endings", async ({ page }) => {
  await page.goto("/");
  const source =
    "# Keep this note\r\ncff-version: 1.2.0\r\ntitle: lensgrind\r\nauthors:\r\n  - given-names: Marie\r\n    family-names: Curie\r\n";
  await page
    .locator("#file-picker")
    .setInputFiles({ name: "CITATION.cff", mimeType: "text/plain", buffer: Buffer.from(source) });
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  expect(await page.locator("#output").textContent()).toBe(source);
});

test("a cancelled view transfer cannot overwrite a newer file draft", async ({ page }) => {
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const held = [];
    window.Worker = class extends NativeWorker {
      postMessage(message, ...rest) {
        if (message.payload?.edit) held.push(() => super.postMessage(message, ...rest));
        else super.postMessage(message, ...rest);
      }
    };
    window.releaseTransfers = () => {
      for (const send of held.splice(0)) send();
    };
  });
  await page.goto("/");
  await page.locator("#example").click();
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  await page.getByRole("tab", { name: "Enter details" }).click();
  await expect(page.locator("#message")).toContainText("Opening project details");
  await page.getByRole("tab", { name: "Use a file", exact: true }).click();
  await expect(page.locator("#message")).toBeEmpty();
  await page.locator("#input").fill('[project]\nname="latest optics"\nauthors=[{name="Marie Curie"}]');
  await page.evaluate(() => window.releaseTransfers());
  await expect(page.locator("#output")).toContainText("latest optics");
  await expect(page.locator("#file-tab")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#input")).toHaveValue(/latest optics/);
});

test("a delayed file read cannot replace metadata typed afterwards", async ({ page }) => {
  await page.addInitScript(() => {
    const read = File.prototype.arrayBuffer;
    File.prototype.arrayBuffer = async function () {
      window.fileReadStarted = true;
      await new Promise((resolve) => {
        window.finishFileRead = resolve;
      });
      return read.call(this);
    };
  });
  await page.goto("/");
  await page.locator("#file-picker").setInputFiles({
    name: "package.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"name":"older file","author":"Marie Curie"}'),
  });
  await page.waitForFunction(() => window.fileReadStarted);
  const newer = '{"name":"newer draft","author":"Marie Curie"}';
  await page.locator("#input").fill(newer);
  await page.evaluate(() => window.finishFileRead());
  await expect(page.locator("#copy")).toBeEnabled({ timeout: 90000 });
  await expect(page.locator("#input")).toHaveValue(newer);
  await expect(page.locator("#output")).toContainText("newer draft");
});

test("entry tabs use keyboard activation without losing the current draft", async ({ page }) => {
  await page.goto("/");
  await page.locator("#file-tab").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#form-tab")).toBeFocused();
  await expect(page.locator("#file-panel")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("#form-panel")).toBeVisible();
  await page.locator("#title").fill("partial keyboard draft");
  await page.locator("#title").press("Enter");
  await expect(page.locator("#message")).toHaveAttribute("data-notice", "true");
  await page.locator("#form-tab").focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  await expect(page.locator("#file-panel")).toBeVisible({ timeout: 90000 });
  await expect(page.locator("#input")).toHaveValue(/partial keyboard draft/);
});

test("Python distribution metadata examples and uploads generate citation files", async ({ page }) => {
  await page.goto("/");
  await page.locator("#source-format").selectOption("METADATA");
  await page.locator("#example").click();
  await expect(page.locator("#output")).toContainText("Skłodowska-Curie", { timeout: 90000 });
  await page.locator("#source-format").selectOption("PKG-INFO");
  await expect(page.locator("#input")).toHaveValue(/Metadata-Version: 2\.6/);
  await page.locator("#file-picker").setInputFiles({
    name: "PKG-INFO",
    mimeType: "text/plain",
    buffer: Buffer.from("Metadata-Version: 2.6\nName: optics-kit\nVersion: 2.0.0\nAuthor: Marie Skłodowska-Curie\n"),
  });
  await expect(page.locator("#output")).toContainText("optics-kit");
  await page.locator("#output-file").selectOption(".zenodo.json");
  await expect(page.locator("#output")).toContainText('"upload_type": "software"');
  await accessible(page);
});

import assert from "node:assert/strict";
import test from "node:test";
import { highlightedParts, searchExcerpt, searchSections } from "./docs-search.mjs";

test("documentation search matches full section text and ranks headings first", () => {
  const body = {
    title: "Guide",
    heading: "Install",
    text: "Required fields work across dataset metadata",
    url: "guide/#install",
  };
  const heading = { title: "Required fields", heading: "Dataset metadata", text: "", url: "config/#dataset" };
  assert.deepEqual(searchSections([body, heading], "REQUIRED dataset"), [heading, body]);
  assert.deepEqual(searchSections([body], "  "), []);
  assert.deepEqual(searchSections([body], "absent"), []);
  assert.deepEqual(searchSections([body], "[fields]"), []);
});

test("search excerpts keep word boundaries and highlight query text literally", () => {
  const text = `${"different licences ".repeat(12)}dataset licence records`;
  const excerpt = searchExcerpt(text, "dataset");
  assert.match(excerpt, /^…(?:different|licences)\b/);
  assert.ok(excerpt.includes("dataset"));
  assert.deepEqual(highlightedParts("Use [fields] and <img> safely.", "[fields] <img>"), [
    { text: "Use ", match: false },
    { text: "[fields]", match: true },
    { text: " and ", match: false },
    { text: "<img>", match: true },
    { text: " safely.", match: false },
  ]);
  assert.deepEqual(highlightedParts("Literal .* expression", ".*"), [
    { text: "Literal ", match: false },
    { text: ".*", match: true },
    { text: " expression", match: false },
  ]);
});

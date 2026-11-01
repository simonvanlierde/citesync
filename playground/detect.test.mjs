import assert from "node:assert/strict";
import test from "node:test";
import { detectFormats } from "./detect.mjs";

test("identifies all supported metadata formats without a filename", () => {
  for (const [text, expected] of [
    ["Metadata-Version: 2.6\nName: lensgrind\nVersion: 1.4.0\n", "METADATA"],
    ['[project]\nname="lensgrind"', "pyproject.toml"],
    ['[workspace.package]\nversion="1.0.0"', "Cargo.toml"],
    ["cff-version: 1.2.0\ntitle: lensgrind", "CITATION.cff"],
    [JSON.stringify({ "@context": "https://w3id.org/codemeta/3.0", name: "lensgrind" }), "codemeta.json"],
    [JSON.stringify({ title: "lensgrind", creators: [{ name: "Skłodowska-Curie, Marie" }] }), ".zenodo.json"],
    [JSON.stringify({ name: "lensgrind", author: "Marie Skłodowska-Curie" }), "package.json"],
  ])
    assert.deepEqual(detectFormats(text), [expected]);
});

test("does not silently choose an ambiguous or unrecognised format", () => {
  assert.deepEqual(detectFormats('[project]\nname="one"\n[package]\nname="two"'), ["pyproject.toml", "Cargo.toml"]);
  assert.deepEqual(detectFormats('{"name":"unknown"}'), []);
  assert.deepEqual(detectFormats("not metadata"), []);
  assert.deepEqual(detectFormats("[]"), []);
  assert.deepEqual(detectFormats(""), []);
});

test("handles a BOM and gives CodeMeta precedence over generic npm fields", () => {
  assert.deepEqual(
    detectFormats(
      "\ufeff" +
        JSON.stringify({
          "@context": "https://w3id.org/codemeta/3.0",
          name: "lensgrind",
          version: "1.0.0",
          author: [],
        }),
    ),
    ["codemeta.json"],
  );
});

test("recognises the legacy CodeMeta DOI context and avoids guessing unknown JSON-LD as npm", () => {
  assert.deepEqual(
    detectFormats(
      JSON.stringify({
        "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
        name: "lensgrind",
        version: "1.0.0",
        author: [],
      }),
    ),
    ["codemeta.json"],
  );
  assert.deepEqual(
    detectFormats(JSON.stringify({ "@context": "https://schema.org", name: "unknown", version: "1.0.0" })),
    [],
  );
});

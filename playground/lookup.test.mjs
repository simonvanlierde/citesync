import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { lookupTerms } from "./lookup.mjs";

const { rows } = JSON.parse(fs.readFileSync(new URL("../src/citesync/mapping-local.json", import.meta.url)));

test("field lookup finds a term by its name or another format's path", () => {
  assert.deepEqual(lookupTerms(rows, "  TITLE "), ["name"]);
  assert.deepEqual(lookupTerms(rows, "doi"), ["identifier"]);
  assert.ok(lookupTerms(rows, "given-names").includes("author.givenName"));
  assert.deepEqual(lookupTerms(rows, "no-such-field"), []);
});

test("lookup shows pinned terms and person details, without unrelated formats", () => {
  const terms = lookupTerms(rows, "");
  assert.ok(terms.includes("swhid"));
  assert.ok(terms.includes("contributor.@id"));
  assert.ok(terms.includes("resourceType"));
  assert.ok(terms.includes("publisher"));
  assert.deepEqual(lookupTerms(rows, "crate"), []);
});

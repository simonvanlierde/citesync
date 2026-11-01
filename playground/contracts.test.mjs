import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("the static entry point has no inline code or upload endpoint", () => {
  const html = fs.readFileSync(new URL("index.html", import.meta.url), "utf8");
  assert.match(html, /Content-Security-Policy/);
  assert.doesNotMatch(html, /<style|\son\w+=|<script(?![^>]*\bsrc=)/i);
  assert.match(html, /form-action 'none'/);
});

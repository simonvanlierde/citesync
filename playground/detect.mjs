const cff = /^cff-version\s*:/m;
const python = /^\s*\[project(?:\.[^\]]+)?\]\s*(?:#.*)?$/m;
const cargo = /^\s*\[(?:package|workspace)(?:\.[^\]]+)?\]\s*(?:#.*)?$/m;
const npmKeys = [
  "author",
  "contributors",
  "version",
  "scripts",
  "dependencies",
  "devDependencies",
  "private",
  "repository",
  "license",
];

export function detectFormats(text) {
  const value = text.replace(/^\uFEFF/, "");
  const found = [];
  if (/^Metadata-Version:\s*\d+\.\d+\s*$/m.test(value) && /^Name:\s*\S/m.test(value)) found.push("METADATA");
  if (/^Package:\s*\S/m.test(value) && /^(?:Title|Version|Authors@R):/m.test(value)) found.push("DESCRIPTION");
  if (
    !python.test(value) &&
    !cargo.test(value) &&
    (/^\s*uuid\s*=\s*["'][0-9a-fA-F-]{36}["']/m.test(value) ||
      /^\s*\[(?:deps|compat|extras|targets|sources)\]\s*$/m.test(value))
  )
    found.push("Project.toml");
  if (cff.test(value)) found.push("CITATION.cff");
  if (python.test(value)) found.push("pyproject.toml");
  if (cargo.test(value)) found.push("Cargo.toml");
  try {
    const data = JSON.parse(value);
    if (!data || Array.isArray(data) || typeof data !== "object") return found;
    const contexts = [data["@context"]].flat();
    const codemeta =
      contexts.some(
        (context) =>
          typeof context === "string" &&
          (context.includes("w3id.org/codemeta/") || context === "https://doi.org/10.5063/schema/codemeta-2.0"),
      ) || [data["@type"], data.type].flat().includes("SoftwareSourceCode");
    if (codemeta) found.push("codemeta.json");
    if ("upload_type" in data || "creators" in data) found.push(".zenodo.json");
    if (!codemeta && !("@context" in data) && typeof data.name === "string" && npmKeys.some((key) => key in data))
      found.push("package.json");
  } catch {
    // Incomplete JSON is left for the filename override rather than guessed.
  }
  return found;
}

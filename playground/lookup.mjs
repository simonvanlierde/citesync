const formats = [
  ["cff-1.2.0", "CITATION.cff"],
  ["codemeta", "codemeta.json"],
  ["zenodo", ".zenodo.json"],
  ["pep621", "pyproject.toml"],
  ["cargo", "Cargo.toml"],
  ["npm", "package.json"],
];

export function lookupTerms(rows, query) {
  const needle = query.trim().toLowerCase();
  return [
    ...new Set(
      rows
        .filter((row) => formats.some(([format]) => format === row.format))
        .filter((row) => `${row.term} ${row.path || ""}`.toLowerCase().includes(needle))
        .map((row) => row.term),
    ),
  ];
}

export function fieldLookup() {
  const disclosure = document.querySelector("#field-lookup");
  const search = document.querySelector("#field-search");
  const status = document.querySelector("#lookup-status");
  const results = document.querySelector("#lookup-results");
  const retry = document.querySelector("#lookup-retry");
  let mapping;
  let loading = false;

  function render() {
    const terms = lookupTerms(mapping.rows, search.value);
    status.textContent = terms.length
      ? `${terms.length} matching ${terms.length === 1 ? "field" : "fields"}`
      : "No matching fields. Try a CodeMeta term or a field name.";
    results.replaceChildren();
    for (const [format, filename] of terms.length ? formats : []) {
      const card = document.createElement("section");
      const heading = document.createElement("h3");
      heading.textContent = filename;
      const list = document.createElement("dl");
      for (const term of terms) {
        const name = document.createElement("dt");
        name.textContent = term;
        const value = document.createElement("dd");
        const path = mapping.rows.find((row) => row.format === format && row.term === term)?.path;
        const content = document.createElement(path ? "code" : "span");
        content.textContent = path || "Not represented in this mapping";
        value.append(content);
        list.append(name, value);
      }
      card.append(heading, list);
      results.append(card);
    }
  }

  async function load() {
    if (mapping || loading) return;
    loading = true;
    retry.hidden = true;
    status.textContent = "Loading field mappings…";
    try {
      const response = await fetch(new URL("./lookup.json", import.meta.url));
      if (!response.ok) throw new Error("Mapping unavailable");
      mapping = await response.json();
      const source = document.querySelector("#lookup-source");
      source.textContent = `codemeta-drift ${mapping.tag}`;
      source.href = `https://github.com/simonvanlierde/codemeta-drift/tree/${mapping.commit}`;
      source.hidden = false;
      render();
    } catch {
      mapping = undefined;
      status.textContent = "Field mappings could not load. Retry to load them again.";
      retry.hidden = false;
    } finally {
      loading = false;
    }
  }

  disclosure.addEventListener("toggle", () => {
    if (disclosure.open) load();
  });
  retry.addEventListener("click", load);
  search.addEventListener("input", () => {
    if (mapping) render();
  });
}

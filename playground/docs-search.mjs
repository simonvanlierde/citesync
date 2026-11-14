export function searchSections(index, query) {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  return index
    .map((section) => {
      const heading = `${section.title} ${section.heading}`.toLocaleLowerCase();
      const text = `${heading} ${section.text.toLocaleLowerCase()}`;
      return {
        section,
        score: terms.filter((term) => heading.includes(term)).length,
        matches: terms.every((term) => text.includes(term)),
      };
    })
    .filter((result) => result.matches)
    .sort((a, b) => b.score - a.score)
    .map((result) => result.section);
}

export function searchExcerpt(text, query) {
  const positions = query
    .toLocaleLowerCase()
    .trim()
    .split(/\s+/)
    .map((term) => text.toLocaleLowerCase().indexOf(term))
    .filter((at) => at >= 0);
  let start = Math.max(0, (positions.length ? Math.min(...positions) : 0) - 60);
  while (start > 0 && /\S/.test(text[start - 1])) start--;
  let end = Math.min(text.length, start + 220);
  while (end > start && end < text.length && /\S/.test(text[end])) end--;
  if (end === start) end = Math.min(text.length, start + 220);
  return `${start ? "…" : ""}${text.slice(start, end).trim()}${end < text.length ? "…" : ""}`;
}

export function highlightedParts(text, query) {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const lower = text.toLocaleLowerCase();
  const parts = [];
  let cursor = 0;
  while (cursor < text.length) {
    const next = terms
      .map((term) => ({ at: lower.indexOf(term, cursor), length: term.length }))
      .filter(({ at }) => at >= 0)
      .sort((a, b) => a.at - b.at || b.length - a.length)[0];
    if (!next) {
      parts.push({ text: text.slice(cursor), match: false });
      break;
    }
    if (next.at > cursor) parts.push({ text: text.slice(cursor, next.at), match: false });
    parts.push({ text: text.slice(next.at, next.at + next.length), match: true });
    cursor = next.at + next.length;
  }
  return parts;
}

function highlight(element, text, query) {
  for (const part of highlightedParts(text, query)) {
    if (part.match) {
      const mark = document.createElement("mark");
      mark.textContent = part.text;
      element.append(mark);
    } else element.append(document.createTextNode(part.text));
  }
}

if (typeof document !== "undefined") {
  const search = document.querySelector(".docs-search");
  const input = document.querySelector("#docs-search");
  const status = document.querySelector("#docs-search-status");
  const results = document.querySelector("#docs-search-results");
  const retry = document.querySelector("#docs-search-retry");
  const more = document.querySelector("#docs-search-more");
  const root = new URL(search.dataset.root, window.location.href);
  let index;
  let failed = false;
  search.hidden = false;

  function render() {
    results.replaceChildren();
    results.hidden = true;
    more.hidden = true;
    const query = input.value.trim();
    if (!index) {
      status.textContent = failed ? "Search could not load. Retry, or browse the guides below." : "Loading search…";
      return;
    }
    if (!query) {
      status.textContent = "Search all guides. Your search stays in this browser.";
      return;
    }
    const matches = searchSections(index, query);
    status.textContent = matches.length
      ? `${matches.length} matching section${matches.length === 1 ? "" : "s"}.`
      : "No matching sections. Try a command, file name or shorter phrase.";
    for (const section of matches) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = new URL(section.url, root).href;
      highlight(
        link,
        section.heading === section.title ? section.title : `${section.title} — ${section.heading}`,
        query,
      );
      const snippet = document.createElement("p");
      highlight(snippet, searchExcerpt(section.text, query), query);
      item.append(link, snippet);
      results.append(item);
    }
    results.hidden = !matches.length;
    more.hidden = !matches.length || results.scrollHeight <= results.clientHeight;
    more.textContent = `Scroll the results to read all ${matches.length} matching sections.`;
  }

  async function load() {
    failed = false;
    retry.hidden = true;
    render();
    try {
      const response = await fetch(new URL("search-index.json", root));
      if (!response.ok) throw new Error("Search index unavailable");
      index = await response.json();
    } catch {
      failed = true;
      retry.hidden = false;
    }
    render();
  }
  input.addEventListener("input", render);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      input.value = "";
      render();
    }
  });
  retry.addEventListener("click", load);
  const navigation = document.querySelector(".docs-sidebar details");
  const narrow = window.matchMedia("(max-width: 800px)");
  function adaptNavigation() {
    navigation.open = !narrow.matches;
  }
  narrow.addEventListener("change", adaptNavigation);
  adaptNavigation();
  load();
}

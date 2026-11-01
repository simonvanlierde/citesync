// A searchable list for a native <select>, as the WAI-ARIA editable combobox pattern describes.
// The select stays the source of truth: other code reads its value and listens for its change event.
const setValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
const key = (text) => text.replace(/^\./, "").toLowerCase();

/** Sort options by name inside each group, ignoring a leading dot, so `.zenodo.json` sorts as zenodo. */
export function byName(a, b) {
  return key(a).localeCompare(key(b));
}

export function picker(select) {
  const input = document.createElement("input");
  const list = document.createElement("ul");
  const wrap = document.createElement("div");
  input.id = `${select.id}-search`;
  input.type = "text";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", `${select.id}-list`);
  list.id = `${select.id}-list`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  wrap.className = "picker";
  wrap.append(input, list);
  select.after(wrap);
  select.hidden = true;
  for (const label of document.querySelectorAll(`label[for="${select.id}"]`)) {
    label.htmlFor = input.id;
    list.setAttribute("aria-label", label.textContent);
  }
  const options = () => [...list.querySelectorAll('[role="option"]')].filter((item) => !item.hidden);
  const current = () => select.selectedOptions[0];
  const show = () => {
    input.value = current()?.text ?? "";
  };
  let active;
  let query = ""; // what the person typed; a click opens the full list while the input shows the chosen name
  const activate = (item) => {
    active?.classList.remove("active");
    active = item;
    if (!item) {
      input.removeAttribute("aria-activedescendant");
      return;
    }
    item.classList.add("active");
    input.setAttribute("aria-activedescendant", item.id);
    // scroll the list only: scrollIntoView would also scroll the page when the list runs past the window
    if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight;
    }
  };
  const open = (text) => {
    query = text;
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    for (const group of list.children) {
      let shown = 0;
      for (const item of group.querySelectorAll('[role="option"]')) {
        const text = `${item.textContent} ${item.dataset.value} ${group.dataset.label ?? ""}`.toLowerCase();
        item.hidden = !terms.every((term) => text.includes(term));
        shown += item.hidden ? 0 : 1;
      }
      group.hidden = shown === 0;
    }
    const matches = options();
    list.dataset.empty = String(matches.length === 0);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    // a name that starts with the query beats one found through its group, as "py" means pyproject.toml
    const start = terms.length ? matches.find((item) => key(item.textContent).startsWith(key(terms[0]))) : undefined;
    activate(start ?? matches.find((item) => item.dataset.value === select.value) ?? matches[0]);
  };
  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    activate(undefined);
    show();
  };
  const choose = (item) => {
    const changed = item.dataset.value !== select.value;
    setValue.call(select, item.dataset.value);
    close();
    if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const build = () => {
    const groups = select.querySelectorAll("optgroup").length
      ? [...select.children].map((child) => (child.tagName === "OPTGROUP" ? child : { label: "", children: [child] }))
      : [{ label: "", children: [...select.options] }];
    list.replaceChildren(
      ...groups.map((group, g) => {
        const item = document.createElement("li");
        item.setAttribute("role", "presentation");
        item.dataset.label = group.label;
        const members = document.createElement("ul");
        members.setAttribute("role", "group");
        if (group.label) {
          const heading = document.createElement("div");
          heading.className = "picker-group";
          heading.id = `${list.id}-g${g}`;
          heading.textContent = group.label;
          members.setAttribute("aria-labelledby", heading.id);
          item.append(heading);
        }
        for (const [o, option] of [...group.children].entries()) {
          if (option.disabled) continue;
          const choice = document.createElement("li");
          choice.id = `${list.id}-${g}-${o}`;
          choice.setAttribute("role", "option");
          choice.dataset.value = option.value;
          choice.textContent = option.text;
          members.append(choice);
        }
        item.append(members);
        return item;
      }),
    );
    for (const item of list.querySelectorAll('[role="option"]')) {
      item.setAttribute("aria-selected", String(item.dataset.value === select.value));
    }
    input.size = Math.max(10, ...[...select.options].map((option) => option.text.length)); // as wide as a select
    if (list.hidden) show();
    else open(query); // a refresh while the list is open keeps what the person typed
  };
  // code sets select.value directly, which fires no event, so the shown text follows the setter
  Object.defineProperty(select, "value", {
    configurable: true,
    get: Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").get.bind(select),
    set(value) {
      setValue.call(select, value);
      build();
    },
  });
  new MutationObserver(build).observe(select, { childList: true, subtree: true });
  input.addEventListener("input", () => open(input.value));
  input.addEventListener("click", () => {
    if (list.hidden) {
      input.select();
      open("");
    }
  });
  input.addEventListener("keydown", (event) => {
    const matches = options();
    const at = matches.indexOf(active);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.hidden || event.altKey) {
        open("");
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      activate(matches[Math.min(Math.max(at + step, 0), matches.length - 1)]);
    } else if (event.key === "Enter" && !list.hidden) {
      event.preventDefault();
      if (active) choose(active);
    } else if (event.key === "Escape" && !list.hidden) {
      event.preventDefault();
      close();
    }
  });
  input.addEventListener("blur", close);
  list.addEventListener("mousedown", (event) => event.preventDefault()); // keep focus in the input
  list.addEventListener("click", (event) => {
    const item = event.target.closest('[role="option"]');
    if (item) choose(item);
  });
  build();
  return input;
}

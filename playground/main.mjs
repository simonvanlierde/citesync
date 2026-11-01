import { detectFormats } from "./detect.mjs";

const $ = (selector) => document.querySelector(selector);
let mode = "file";
let selected = "CITATION.cff";
let result;
let revision = 0;
let sequence = 0;
let worker;
let pending;
let timeout;
let ready = false;
let busy = false;
let debounce;
let startupTimeout;
let queued = false;
let blocked = false;
let namesDraft;
let resultRevision = -1;
let fileHint;
let originalFile;
let fileRead = 0;
let exampleText;
let formDocument = {};
let formSnapshot;
let savedNames;
let modeTransition = 0;
const transfers = new Map();
const filenames = [
  "CITATION.cff",
  "codemeta.json",
  ".zenodo.json",
  "pyproject.toml",
  "Cargo.toml",
  "package.json",
  "PKG-INFO",
  "METADATA",
  "DESCRIPTION",
  "Project.toml",
  "JuliaProject.toml",
];
const outputLabels = {
  "CITATION.cff": "CITATION.cff — GitHub citation",
  "codemeta.json": "codemeta.json — Software metadata",
  ".zenodo.json": ".zenodo.json — Zenodo deposit",
  "citation.bib": "citation.bib — BibTeX",
  "citation.csl.json": "citation.csl.json — CSL-JSON",
};
const examples = {
  "pyproject.toml":
    '[project]\nname = "lensgrind"\nversion = "1.4.0"\ndescription = "Measure microscope optics."\nauthors = [{name = "Antonie van Leeuwenhoek"}]\nlicense = "Apache-2.0"\n',
  "Cargo.toml":
    '[package]\nname = "lensgrind"\nversion = "1.4.0"\ndescription = "Measure microscope optics."\nauthors = ["Antonie van Leeuwenhoek"]\nlicense = "Apache-2.0"\n',
  "package.json": JSON.stringify(
    {
      name: "lensgrind",
      version: "1.4.0",
      description: "Measure microscope optics.",
      author: "Antonie van Leeuwenhoek",
      license: "Apache-2.0",
    },
    null,
    2,
  ),
  "codemeta.json": JSON.stringify(
    {
      "@context": "https://w3id.org/codemeta/3.0",
      "@type": "SoftwareSourceCode",
      name: "lensgrind",
      version: "1.4.0",
      description: "Measure microscope optics.",
      author: [{ "@type": "Person", givenName: "Antonie", familyName: "van Leeuwenhoek" }],
      license: "https://spdx.org/licenses/Apache-2.0",
    },
    null,
    2,
  ),
  ".zenodo.json": JSON.stringify(
    {
      title: "lensgrind",
      version: "1.4.0",
      description: "Measure microscope optics.",
      creators: [{ name: "van Leeuwenhoek, Antonie" }],
      license: "Apache-2.0",
      upload_type: "software",
    },
    null,
    2,
  ),
  "CITATION.cff":
    'cff-version: 1.2.0\nmessage: "Please cite this software using these metadata."\ntitle: lensgrind\nversion: 1.4.0\nabstract: Measure microscope optics.\nlicense: Apache-2.0\nauthors:\n  - given-names: Antonie\n    family-names: van Leeuwenhoek\n',
};
examples.METADATA =
  "Metadata-Version: 2.6\nName: lensgrind\nVersion: 1.4.0\nSummary: Measure microscope optics.\nAuthor: Marie Skłodowska-Curie\nLicense-Expression: Apache-2.0\n";
examples["PKG-INFO"] = examples.METADATA;
examples.DESCRIPTION = `Package: lensgrind
Title: Measure Microscope Optics
Version: 1.4-2
Description: Measure microscope optics.
Authors@R: person("Marie", "Skłodowska-Curie", role = c("aut", "cre"))
License: GPL (>= 2)
Encoding: UTF-8
`;
examples["Project.toml"] = `name = "Lensgrind"
uuid = "00000000-0000-0000-0000-000000000001"
version = "1.4.2"
authors = [{given-names = "Marie", family-names = "Skłodowska-Curie"}]
`;
examples["JuliaProject.toml"] = examples["Project.toml"];

function announce(text, { error = false, inputError = false, notice = error } = {}) {
  if ($("#message").textContent !== text) $("#message").textContent = text;
  $("#message").dataset.error = String(error);
  $("#message").dataset.notice = String(notice);
  $("#message").setAttribute("role", error ? "alert" : "status");
  $("#input").setAttribute("aria-invalid", String(inputError && mode === "file"));
}
function progress(waiting) {
  $("#status").dataset.notice = "false";
  $("#status").textContent = waiting ? "Updating preview…" : "";
  $("#output-panel").setAttribute("aria-busy", String(waiting));
}
function exportsEnabled(enabled) {
  for (const id of ["zip", "copy", "download"]) $(`#${id}`).disabled = !enabled;
}
function invalidate(resetNames = true) {
  progress(false);
  revision++;
  queued = false;
  clearTimeout(debounce);
  exportsEnabled(false);
  if (resetNames) {
    namesDraft = undefined;
    $("#name-review").hidden = true;
  }
  if (result) {
    $("#output-panel").dataset.stale = "true";
  }
  if (!blocked) announce("");
  debounce = setTimeout(generate, 100);
}
function authorRow({ given = "", family = "", metadata = {}, organization = false } = {}) {
  const row = document.createElement("fieldset");
  row.className = "author-row";
  row.authorData = { metadata, organization };
  const index = ++sequence;
  const legend = document.createElement("legend");
  legend.textContent = "Author";
  row.append(legend);
  const fields = document.createElement("div");
  fields.className = "fields";
  for (const [key, label, value] of [
    ["given", "Given names", given],
    ["family", "Family names", family],
  ]) {
    const container = document.createElement("div");
    const name = document.createElement("label");
    name.htmlFor = `author-${index}-${key}`;
    name.textContent = organization && key === "family" ? "Organisation name" : label;
    const input = document.createElement("input");
    input.id = name.htmlFor;
    input.dataset.part = key;
    input.value = value;
    input.maxLength = 500;
    input.autocomplete = "off";
    if (key === "family") input.required = true;
    container.hidden = organization && key === "given";
    container.append(name, input);
    fields.append(container);
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "link";
  remove.textContent = "Remove author";
  remove.addEventListener("click", () => {
    if ($("#authors").children.length === 1) {
      announce("Keep at least one author.", { error: true });
      return;
    }
    row.remove();
    invalidate();
    $("#add-author").focus();
  });
  row.append(fields, remove);
  $("#authors").append(row);
}
function payload() {
  if (mode === "file") {
    const value = $("#input").value;
    const text = originalFile?.value === value ? originalFile.text : value;
    if (!text.trim()) {
      $("#detected-format").textContent = "";
      announce("Paste or open metadata to see your citation files.");
      return;
    }
    let filename = $("#source-format").value;
    if (filename === "auto") {
      const candidates = fileHint ? [fileHint] : detectFormats(text);
      if (candidates.length !== 1) {
        $("#detected-format").textContent = candidates.length
          ? `Could be ${candidates.join(" or ")}. Choose a filename above.`
          : "Format not recognised yet. Keep typing or choose a filename above.";
        announce("");
        return;
      }
      [filename] = candidates;
      $("#detected-format").textContent = `Detected ${filename}`;
    } else {
      $("#detected-format").textContent = `Using ${filename}`;
    }
    return { filename, text };
  }
  const details = formDetails();
  if (!details.title.trim() || details.authors.some((author) => !author.family.trim())) {
    announce("Enter a software title and each author’s family name to see your files.", { notice: true });
    return;
  }
  if (!$("#form-panel").checkValidity()) {
    announce("Enter a complete repository URL, such as https://example.org/project.", { notice: true });
    return;
  }
  return { details };
}
function startWorker() {
  $("#runtime").hidden = false;
  $("#runtime").textContent = "Loading the converter… You can keep editing.";
  startupTimeout = setTimeout(failedLoad, 90000);
  worker = new Worker(new URL("./worker.mjs", import.meta.url), { type: "module" });
  worker.onmessage = ({ data }) => {
    if (data.type === "setup") {
      $("#runtime").textContent = "Finishing converter setup… You can keep editing.";
      return;
    }
    if (data.type === "ready") {
      clearTimeout(startupTimeout);
      ready = true;
      $("#runtime").hidden = true;
      $("#version-label").textContent = data.version;
      return;
    }
    if (data.type === "load-error") return failedLoad();
    const transfer = transfers.get(data.id);
    if (transfer) {
      clearTimeout(transfer.timer);
      transfers.delete(data.id);
      if (data.type === "input-error") transfer.reject(new Error(data.error));
      else transfer.resolve(data.result);
      return;
    }
    if (!pending || data.id !== pending.id) return;
    clearTimeout(timeout);
    busy = false;
    const request = pending;
    pending = undefined;
    if (request.revision !== revision) {
      if (queued) generate();
      return;
    }
    progress(false);
    if (data.type === "input-error") {
      announce(data.error, { error: true, inputError: true });
      return;
    }
    result = data.result;
    resultRevision = request.revision;
    render();
    if (request.archive && result.zip)
      download(
        Uint8Array.from(atob(result.zip), (char) => char.charCodeAt(0)),
        "citesync-files.zip",
        "application/zip",
      );
  };
  worker.onerror = (event) => {
    event.preventDefault();
    failedLoad();
  };
}
function failedLoad() {
  progress(false);
  for (const transfer of transfers.values()) {
    clearTimeout(transfer.timer);
    transfer.reject(new Error("The converter could not load. Your drafts are still here. Retry to switch views."));
  }
  transfers.clear();
  clearTimeout(timeout);
  clearTimeout(startupTimeout);
  blocked = true;
  worker?.terminate();
  worker = undefined;
  ready = false;
  busy = false;
  pending = undefined;
  $("#runtime").hidden = true;
  announce("The converter could not load. Your input is still here. Check your connection, then retry.", {
    error: true,
  });
  $("#retry").hidden = false;
  exportsEnabled(false);
}
function generate(archive = false) {
  progress(false);
  if (blocked) return;
  const request = payload();
  if (!request) return;
  request.archive = archive;
  if (namesDraft) {
    if (namesDraft.some((name) => !name.family.trim())) {
      announce("Add each reviewed family name to update the preview.", { notice: true });
      return;
    }
    request.names = namesDraft;
  }
  progress(true);
  if (busy) {
    queued = true;
    return;
  }
  queued = false;
  busy = true;
  exportsEnabled(false);
  $("#retry").hidden = true;
  if (!ready) announce("Preparing the converter. Your preview will appear automatically…");
  pending = { id: ++sequence, revision, archive };
  timeout = setTimeout(failedLoad, 90000);
  if (!worker) startWorker();
  worker.postMessage({ id: pending.id, payload: request });
}
function syncExports() {
  if (!result) return;
  const errors = result.findings.some((finding) => finding.severity === "error");
  const current = resultRevision === revision && !busy;
  exportsEnabled(current && !errors && !blocked);
  if (!current) return;
  $("#status").dataset.notice = String(errors);
  $("#status").textContent = errors ? "Resolve the conversion problems before exporting." : "";
}
function isTemplate() {
  return selected in result.templates;
}
function selectOutput(filename) {
  selected = filename;
  $("#output-file").value = filename;
  $("#output").textContent = isTemplate() ? result.templates[filename] : result.files[filename];
  $("#filename-note").hidden = filename !== ".zenodo.json";
  $("#template-warning").hidden = !isTemplate();
  $("#zip").hidden = isTemplate();
  $("#template-notes").replaceChildren(
    ...result.template_notes
      .filter((note) => note.startsWith(`${filename}:`))
      .map((note) => {
        const item = document.createElement("li");
        item.textContent = note;
        return item;
      }),
  );
}
function render() {
  $("#empty-result").hidden = true;
  for (const id of ["output-choice", "output-panel", "exports"]) $(`#${id}`).hidden = false;
  $("#output-panel").dataset.stale = "false";
  const outputNames = [...Object.keys(result.files), ...Object.keys(result.templates)];
  if (
    [...$("#output-file").options]
      .filter((option) => !option.disabled)
      .map((option) => option.value)
      .join() !== outputNames.join()
  ) {
    $("#output-file").replaceChildren();
    for (const [label, files] of [
      ["Citation files", result.files],
      ["Package templates · incomplete", result.templates],
    ]) {
      const group = document.createElement("optgroup");
      group.label = label;
      for (const filename of Object.keys(files)) {
        group.append(
          new Option(
            label === "Citation files" ? outputLabels[filename] || filename : `${filename} (incomplete)`,
            filename,
          ),
        );
      }
      $("#output-file").append(group);
    }
  }
  selectOutput(outputNames.includes(selected) ? selected : "CITATION.cff");
  $("#name-review").hidden = result.review.length === 0;
  if (!namesDraft) {
    const uncertain = result.review.some(
      ({ original }) =>
        original.trim().split(/\s+/).length !== 2 ||
        /[,;.\d]|\p{Script=Han}|\p{Script=Hangul}|\p{Script=Hiragana}|\p{Script=Katakana}/u.test(original),
    );
    $("#name-review").open = uncertain;
    $("#review-title").textContent = uncertain ? "Check the name split (optional)" : "Author names";
  }
  if (!namesDraft) {
    $("#review-fields").replaceChildren();
    for (const [index, name] of result.review.entries()) {
      const group = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.className = "name-original";
      legend.textContent = name.original;
      group.append(legend);
      const fields = document.createElement("div");
      fields.className = "fields";
      for (const [part, label] of [
        ["given", "Given names"],
        ["family", "Family names"],
      ]) {
        const container = document.createElement("div");
        const text = document.createElement("label");
        text.htmlFor = `review-${index}-${part}`;
        text.textContent = label;
        const input = document.createElement("input");
        input.id = text.htmlFor;
        input.value = name[part];
        input.dataset.part = part;
        input.maxLength = 500;
        container.append(text, input);
        fields.append(container);
      }
      group.append(fields);
      $("#review-fields").append(group);
    }
  }
  const errors = result.findings.filter((finding) => finding.severity === "error");
  const notes = [
    ...result.notes,
    ...result.findings
      .filter((finding) => finding.severity !== "info")
      .map((finding) => `${finding.file ? `${finding.file}: ` : ""}${finding.message} ${finding.help}`),
  ];
  $("#notes").replaceChildren(
    ...notes.map((note) => {
      const item = document.createElement("li");
      item.textContent = note;
      return item;
    }),
  );
  $("#details-notes").hidden = notes.length === 0;
  $("#details-notes").open = errors.length > 0;
  syncExports();
  announce("");
}
function download(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function openFile(file) {
  if (!file) return;
  const read = ++fileRead;
  const inputRevision = revision;
  const current = () => read === fileRead && inputRevision === revision;
  $("#file-picker").value = "";
  if (file.size > 1000000) {
    announce("Choose a metadata file smaller than 1 MB.", { error: true });
    return;
  }
  try {
    const content = await file.arrayBuffer();
    if (!current()) return;
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(content);
    exampleText = undefined;
    $("#input").value = text;
    originalFile = { text, value: $("#input").value };
    $("#source-format").value = "auto";
    fileHint = filenames.includes(file.name) ? file.name : undefined;
    invalidate();
  } catch {
    if (!current()) return;
    announce("The file could not be read as UTF-8 text. Check its encoding, then try again.", { error: true });
  }
}
function formDetails() {
  const details = Object.fromEntries(new FormData($("#form-panel")));
  details.document = formDocument;
  details.authors = [...$("#authors").children].map((row) => ({
    ...row.authorData,
    ...Object.fromEntries([...row.querySelectorAll("input")].map((input) => [input.dataset.part, input.value])),
  }));
  return details;
}
function fillForm(details) {
  for (const input of $("#form-panel").querySelectorAll("input[name]")) {
    input.value = details[input.name] || "";
  }
  formDocument = details.document;
  $("#authors").replaceChildren();
  for (const author of details.authors) authorRow(author);
  if (!details.authors.length) authorRow();
}
function transferRequest(payload) {
  if (blocked)
    return Promise.reject(new Error("The converter is unavailable. Your draft is kept; retry to switch views."));
  if (!worker) startWorker();
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      transfers.delete(id);
      reject(new Error("Switching views timed out. Your draft is kept. Try again."));
    }, 90000);
    transfers.set(id, { resolve, reject, timer });
    worker.postMessage({ id, payload });
  });
}
function showMode(entry, resetNames = true) {
  mode = entry;
  for (const other of ["file", "form"]) {
    $(`#${other}-panel`).hidden = other !== entry;
    $(`#${other}-tab`).setAttribute("aria-selected", String(other === entry));
    $(`#${other}-tab`).tabIndex = other === entry ? 0 : -1;
  }
  invalidate(resetNames);
}
async function setMode(entry) {
  const transition = ++modeTransition;
  if (mode === entry) {
    announce("");
    return;
  }
  const sourceRevision = revision;
  const stillCurrent = () => transition === modeTransition && sourceRevision === revision;
  if (entry === "form") {
    savedNames = namesDraft;
    const request = $("#input").value.trim() ? payload() : undefined;
    if (request) {
      announce("Opening project details…");
      try {
        const response = await transferRequest({
          ...request,
          ...(namesDraft ? { names: namesDraft } : {}),
          edit: true,
        });
        if (!stillCurrent()) return;
        fillForm(response.details);
      } catch (error) {
        if (!stillCurrent()) return;
        formSnapshot = JSON.stringify(formDetails());
        showMode(entry);
        clearTimeout(debounce);
        announce(`${error.message} Your file draft is kept in Use a file.`, { notice: true });
        return;
      }
    }
    formSnapshot = JSON.stringify(formDetails());
    showMode(entry);
    if (!request && $("#input").value.trim()) {
      clearTimeout(debounce);
      announce("Choose the file format in Use a file to import it. Your file and previous details are kept.", {
        notice: true,
      });
    }
    return;
  }
  const details = formDetails();
  if (JSON.stringify(details) === formSnapshot) {
    namesDraft = savedNames;
    showMode(entry, false);
    return;
  }
  announce("Opening the file draft…");
  try {
    const response = await transferRequest({ details, draft: true });
    if (!stillCurrent()) return;
    originalFile = undefined;
    $("#input").value = response.draft;
    $("#source-format").value = "codemeta.json";
    fileHint = undefined;
    exampleText = undefined;
    showMode(entry);
  } catch (error) {
    if (stillCurrent()) announce(error.message, { notice: true });
  }
}
for (const entry of ["file", "form"]) {
  $(`#${entry}-tab`).addEventListener("click", () => setMode(entry));
}
for (const list of document.querySelectorAll('[role="tablist"]')) {
  list.addEventListener("keydown", (event) => {
    const tabs = [...list.querySelectorAll('[role="tab"]')];
    const index = tabs.indexOf(document.activeElement);
    if (index < 0 || !["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    for (const tab of tabs) tab.tabIndex = tab === tabs[next] ? 0 : -1;
    tabs[next].focus();
    if (list.id !== "entry-tabs") tabs[next].click();
  });
}
$("#input").addEventListener("input", () => {
  originalFile = undefined;
  exampleText = undefined;
  fileHint = undefined;
  invalidate();
});
$("#source-format").addEventListener("change", () => {
  const filename = $("#source-format").value;
  if (exampleText !== undefined && $("#input").value === exampleText && filename in examples) {
    originalFile = undefined;
    exampleText = examples[filename];
    $("#input").value = exampleText;
  }
  fileHint = undefined;
  invalidate();
});
$("#form-panel").addEventListener("input", () => invalidate());
$("#form-panel").addEventListener("submit", (event) => {
  event.preventDefault();
  generate();
});
$("#retry").addEventListener("click", () => {
  blocked = false;
  $("#retry").hidden = true;
  startWorker();
  worker.postMessage({ type: "warmup" });
  generate();
});
$("#add-author").addEventListener("click", () => {
  authorRow();
  invalidate();
  $("#authors").lastElementChild.querySelector("input").focus();
});
$("#review-fields").addEventListener("input", () => {
  namesDraft = [...$("#review-fields").children].map((row) =>
    Object.fromEntries([...row.querySelectorAll("input")].map((input) => [input.dataset.part, input.value])),
  );
  invalidate(false);
});
$("#example").addEventListener("click", () => {
  const chosen = $("#source-format").value;
  const detected = detectFormats($("#input").value);
  const filename = chosen === "auto" ? (detected.length === 1 ? detected[0] : "pyproject.toml") : chosen;
  fileHint = undefined;
  originalFile = undefined;
  exampleText = examples[filename];
  $("#input").value = exampleText;
  invalidate();
});
$("#open").addEventListener("click", () => $("#file-picker").click());
$("#file-picker").addEventListener("change", (event) => openFile(event.target.files[0]));
$("#file-panel").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("#input").classList.add("drop-active");
});
$("#file-panel").addEventListener("dragleave", () => $("#input").classList.remove("drop-active"));
$("#file-panel").addEventListener("drop", (event) => {
  event.preventDefault();
  $("#input").classList.remove("drop-active");
  openFile(event.dataTransfer.files[0]);
});
$("#copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(isTemplate() ? result.templates[selected] : result.files[selected]);
    announce(`Copied ${selected}.`);
  } catch {
    announce("Copy was blocked by the browser. Download this file instead.");
  }
});
$("#output-file").addEventListener("change", (event) => selectOutput(event.target.value));
$("#download").addEventListener("click", () =>
  download(isTemplate() ? result.templates[selected] : result.files[selected], selected, "text/plain;charset=utf-8"),
);
$("#zip").addEventListener("click", () => generate(true));
for (const name of ["cli", "hook", "ci"]) {
  $(`#use-${name}`).addEventListener("click", () => {
    $("#snippet-status").textContent = "";
    for (const other of ["cli", "hook", "ci"]) {
      $(`#snippet-${other}`).hidden = other !== name;
      $(`#use-${other}`).setAttribute("aria-selected", String(other === name));
      $(`#use-${other}`).tabIndex = other === name ? 0 : -1;
    }
  });
}
for (const button of document.querySelectorAll(".code-copy")) {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.parentElement.querySelector("pre").textContent);
      $("#snippet-status").textContent = "Copied.";
    } catch {
      $("#snippet-status").textContent = "Copy was blocked. Select the code and copy it manually.";
    }
  });
}
authorRow();

startWorker();
worker.postMessage({ type: "warmup" });

# Generate citation files in the browser

The playground accepts one existing metadata file or a form with project details and authors. It uses the Python engine from this checkout through Pyodide 314.0.7 in a worker. Python dependencies come from `uv.lock`, with artifact hashes checked during the build and again when loading. There is no separate JavaScript converter.

## Run locally

```sh
uv sync --locked
pnpm install --frozen-lockfile
just playground
```

Open <http://127.0.0.1:8468>. The page prepares Pyodide from jsDelivr in the background, downloading the converter packages concurrently. Loading feedback changes when the downloads and Python initialization finish and package setup begins; it does not estimate a percentage or completion time. The site serves the current citesync wheel and its dependencies. A network connection is required; offline operation is not promised.

Paste or open CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml, package.json, PKG-INFO, METADATA, R DESCRIPTION or Julia Project.toml/JuliaProject.toml. Pasted content is detected automatically; use the filename selector to override an uncertain result. An opened file with a recognised filename uses that filename. Other text files are detected from their contents. Try an example follows the selected format; in automatic mode it uses the recognised format, or pyproject.toml for an empty or ambiguous input. While the example is unchanged, choosing another input format switches the example too. Editing or opening a real file ends that behaviour. Each request reads only that file, ignores its embedded citesync settings and uses a temporary repository in browser memory. It does not execute package code or fetch metadata from repository links. Inputs are limited to 1 MB.

Switching entry methods transfers project metadata. An unchanged file draft keeps its original text and format. Editing details creates a CodeMeta working copy for the file view, retaining extra CodeMeta fields, author identifiers, affiliations and Role objects. Other formats are projected through the engine: formatting and unmapped fields from CFF or package manifests are not represented in the CodeMeta form. Keep the original file when those matter. Partial drafts transfer too. Invalid file syntax cannot populate the form; the original file and any previous details remain available, with a notice. Failed or superseded transfers cannot overwrite a newer edit. Unchanged uploaded CFF files retain their original line endings until edited.

The form accepts multiple authors with explicit given and family names. Imported one-string names can be edited in an optional Author names disclosure. It opens for potentially ambiguous cases: single or multiple words, initials, punctuation, and East Asian scripts. Two-word names can still have a different order; this is a prompt, not a confidence score. Downloads do not require a confirmation checkbox. Corrections update the preview automatically. Editing the source or switching entry methods disables old downloads immediately, then refreshes after a 100 ms typing pause. Updates keep keyboard focus in the field being edited. Entry-method tabs use arrow keys to move focus and Enter or Space to open a view; snippet tabs update immediately. Drafts remain on the page after an error.

The playground creates CITATION.cff, codemeta.json and .zenodo.json. Existing metadata is updated where the engine supports it. Conversion notes report fields a destination cannot carry. The preview preserves source metadata where the engine does, including CodeMeta Role objects; it does not invent unavailable values. Zenodo output is metadata for review, not a submission to Zenodo.

BibTeX (`citation.bib`, a biblatex-software `@software` entry), CSL-JSON (`citation.csl.json`, type `software`), an APA 7 reference (`citation.apa.txt`) and schema.org JSON-LD for a website (`schema.jsonld`) are also available, the same files [`citesync export`](../docs/export.md) prints. They use the reviewed author names. A release year/date is included only when supplied and readable. They are output formats, not accepted input formats. CSL-JSON follows the [official CSL input schema](https://github.com/citation-style-language/schema/blob/master/schemas/input/csl-data.json).

The output selector groups citation files and **Package templates (incomplete)** together. Citation choices include short destination labels: GitHub, software metadata, Zenodo, BibTeX, CSL-JSON, APA reference and website structured data. Templates are labelled incomplete in the selector, with their limits below the preview actions. It contains metadata-only pyproject.toml, Cargo.toml and package.json, not complete package configurations. Add build settings, source files and dependencies before use. Names and versions that cannot be carried over are omitted with notes; no identifier or version is invented. The npm template is marked private, and only its first author is included because npm has one author slot. Copy is the primary action, followed by downloading the selected file. The secondary citation ZIP is generated only on request, avoiding archive work during previews. Templates download individually; there is no template ZIP.

The ZIP preserves filenames, including the first dot in .zenodo.json. Some browsers strip that dot from an individual download; rename the file or use the ZIP. Clipboard access depends on browser permission.

Conversion notes show omitted values, warnings and errors, with remedies where available. Missing optional fields are not shown as problems. Template notes relate to the selected template.

Field examples remain visible while typing. Version and SPDX help uses native disclosures and official reference links, accessible by keyboard and touch. Validation guidance shares the amber note style; copying and loading keep neutral feedback.

The repository-use section provides copyable CLI commands, a pre-commit/prek hook and GitHub Actions steps, each with a labelled copy icon in its code block. The checks require committed citation files and fail on disagreement; they do not rewrite files.

## Check

```sh
just check
just playground-build
pnpm exec playwright install chromium firefox webkit
pnpm run test:browser
```

Browser tests run the same journeys in Chromium, Firefox and WebKit using Playwright’s pinned browsers. Set `CHROME_PATH` to override only Chromium. CI installs browser system dependencies; local machines need the libraries reported by Playwright. They run actual Pyodide conversion, name correction, form generation, parse-error recovery, runtime-download failure/retry, stale-export protection, typing during startup, ambiguous detection, focus retention, template downloads and accessibility checks. Network assertions check that metadata is not included in requests and drafts are not saved to web storage. Native copy actions run in all three engines. Clipboard contents are also read back in Chromium, which supports Playwright’s clipboard permission grants. Screenshots go in `test-results/`. R imports accept only the documented static Authors@R subset; uploaded R is never evaluated. Julia UUIDs are not DOIs. See [supported files](../docs/formats.md#r-and-julia-imports) for role and licence limits. No physical-device or guaranteed offline test is included.

## Publish

The playground workflow builds and tests pull requests. On main it deploys the same build to GitHub Pages. In the repository's Settings → Pages, choose **GitHub Actions** as the build source before the first deployment. PR browser screenshots are available in the `playground-browser-results` artifact.

Search and sharing metadata are in the initial HTML: a descriptive title, format-specific description, canonical URL and Open Graph/Twitter tags. The canonical deployment URL is <https://simonvanlierde.com/citesync/>, following the account's GitHub Pages domain. The site is deployed through GitHub Actions with HTTPS enforced; metadata alone does not establish indexing.

The build also writes `site/`, with content-versioned JavaScript, styles, worker and wheel URLs. This keeps cached assets from different deployments together. The public runtime manifest and wheels use normal HTTP caching; citation drafts are never cached. CI runs the browser tests against that deployment bundle.

The page has no upload endpoint, analytics or draft storage. A visitor's files stay in memory and disappear on reload. Runtime downloads contact jsDelivr; project links navigate to GitHub. The local server is for development, not public hosting.

# Product

## Platform

web

## Stack

Static HTML, CSS and JavaScript. A worker runs the same citesync wheel as the CLI through pinned Pyodide. Build the wheel from the current checkout and bundle its locked pure-Python dependencies.

## Users and purpose

Help a researcher generate software citation files without installing a tool. Start with one existing metadata file or basic project details. Preview actual generated content automatically while typing, correct inferred names, then copy or download it. Detect inputs conservatively with an explicit override. Transfer metadata between entry methods, preserve unchanged source drafts and keep extra CodeMeta metadata through form edits. Offer BibTeX and CSL-JSON alongside citation metadata; keep incomplete package templates in a separate labelled group. Existing-file comparison and mapping remain secondary links to CLI documentation.

## Constraints

Files stay in browser memory, without uploads, analytics or draft persistence. Runtime assets require a network connection; offline support is not promised. Input is metadata, never executable code or user-supplied configuration. Preserve metadata the engine understands and show its omissions. Exports must match the current input and any name corrections. Name editing is optional. Copying one file leads; template bundles are not offered.

## Accessibility

Label inputs, support keyboard tabs, announce loading/errors, retain drafts on failure and disable stale exports. Check light/dark themes, narrow phones and browser accessibility rules.

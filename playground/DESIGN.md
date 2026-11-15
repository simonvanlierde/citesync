---
name: "citesync"
description: "Open-science index for software citation files and documentation."
colors: {"ground": "#eef5f0", "paper": "#ffffff", "ink": "#18372f", "muted": "#526b60", "line": "#c7d8ce", "accent": "#176149", "wash": "#e7f1eb", "brand": "#123f35", "on-brand": "#ffffff", "brand-muted": "#c6e0d2", "note": "#795009", "note-wash": "#fff1d2", "nav-active": "#28594b", "dark-ground": "#101e1a", "dark-paper": "#172b24", "dark-ink": "#e3efe8", "dark-muted": "#b1c8ba", "dark-line": "#3b5849", "dark-accent": "#a5dbc0", "dark-wash": "#243f32", "dark-brand": "#0b3026", "dark-note": "#ffe0a0", "dark-note-wash": "#49371a"}
typography: {"display": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "32px", "fontWeight": 600, "lineHeight": 1.25, "letterSpacing": "-.025em"}, "headline": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "24px", "fontWeight": 600, "lineHeight": 1.25}, "title": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "18px", "fontWeight": 600, "lineHeight": 1.25}, "body": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "16px", "fontWeight": 400, "lineHeight": 1.55}, "reading": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "17px", "fontWeight": 400, "lineHeight": 1.7}, "label": {"fontFamily": "IBM Plex Sans, Arial, sans-serif", "fontSize": "14px", "fontWeight": 500, "lineHeight": 1.55}, "code": {"fontFamily": "ui-monospace, \"Cascadia Code\", monospace", "fontSize": "14px", "fontWeight": 400, "lineHeight": 1.7}}
rounded: {"control": "6px", "masthead": "10px", "masthead-mobile": "8px", "panel": "12px"}
spacing: {"space-1": "4px", "space-2": "8px", "space-3": "12px", "space-4": "16px", "space-6": "24px", "space-8": "32px"}
components: {"button-primary": {"backgroundColor": "{colors.accent}", "textColor": "{colors.paper}", "rounded": "{rounded.control}", "padding": "8px 14px"}, "button-secondary": {"backgroundColor": "{colors.paper}", "textColor": "{colors.ink}", "rounded": "{rounded.control}", "padding": "8px 14px"}, "button-link": {"backgroundColor": "transparent", "textColor": "{colors.accent}", "rounded": "{rounded.control}", "padding": "8px 14px"}, "input": {"backgroundColor": "{colors.paper}", "textColor": "{colors.ink}", "rounded": "{rounded.control}", "padding": "9px 12px"}, "site-navigation": {"backgroundColor": "{colors.brand}", "textColor": "{colors.brand-muted}", "rounded": "{rounded.control}", "padding": "8px 12px"}, "entry-tabs": {"backgroundColor": "{colors.wash}", "textColor": "{colors.accent}", "rounded": "{rounded.control}", "padding": "8px 14px"}, "workspace-panel": {"backgroundColor": "{colors.paper}", "textColor": "{colors.ink}", "rounded": "{rounded.panel}", "padding": "20px"}, "code-block": {"backgroundColor": "{colors.wash}", "textColor": "{colors.ink}", "rounded": "{rounded.control}", "padding": "16px 64px 16px 16px"}, "disclosure": {"textColor": "{colors.ink}", "typography": "{typography.label}"}}
---

# Design System: citesync

## Overview

**Creative North Star: "Open-science index"** guides the typography, colors and layout.

A deep-green masthead identifies the site. White and jade surfaces keep metadata, generated files and documentation easy to scan. IBM Plex Sans carries interface text and prose; monospace identifies file contents and commands.

Use compact spacing, clear selected states and softly squared controls. Give the work room through aligned panes and controlled reading widths. The related visual family can extend to sourceledger and codemeta-drift; these rules describe citesync's implemented surfaces.

**Key Characteristics:**

- Green identity with restrained jade surfaces.
- Aligned source and output, with visible finishing actions.
- Readable guides in the same visual system.
- Flat surfaces, semantic states and visible keyboard focus.

Layout and component notes describe the current implementation. Preserve product, privacy and accessibility guarantees when changing interactions. Revisit layout choices when evidence supports a clearer flow.

## Colors

The frontmatter records the stylesheet's light palette and its dark replacements. Names without a `dark-` prefix describe light mode. Match each dark replacement to its unprefixed role. The unchanged on-brand and brand-muted colors apply in both themes. Sidecar tonal ramps are derived previews, not implemented theme values.

### Primary

- **Brand green** (`brand`): masthead background; use `on-brand` for its title and `brand-muted` for supporting text.
- **Action green** (`accent`): links, primary actions, selected controls, carets and focus rings.
- **Navigation green** (`nav-active`): selected and hovered masthead links in both themes.

### Secondary

- **Amber notice** (`note`, `note-wash`): actionable errors, omissions and field guidance. Pair the text and surface roles; never signal a problem through color alone.

### Neutral

- **Ground** (`ground`): page background.
- **Paper** (`paper`): panels and controls; also primary-button text.
- **Ink** (`ink`): primary text and file content.
- **Muted** (`muted`): hints, statuses and stale preview text.
- **Line** (`line`): borders and section dividers.
- **Jade wash** (`wash`): editors, previews, code blocks and selected tabs.

**The Role Rule.** Use the semantic CSS properties so the same component follows both themes. Keep masthead foregrounds separate from body foregrounds.

## Typography

**Interface and prose:** IBM Plex Sans, with Arial and sans-serif fallbacks.
**File contents and commands:** the system monospace stack, with Cascadia Code when available.

The frontmatter defines the observed roles. Display is the documentation page heading; headline serves article and repository-use sections. Title labels workspace panes. Body supports the interface; reading supports documentation articles. Label supports controls and hints. Code preserves file structure with ligatures disabled and a tab size of two.

The masthead uses a compact semibold wordmark (25px), with tight tracking (-.025em). It reduces on phones (22px, then 21px below 401px). Documentation headings reduce on phones (28px). Editable file text increases on phones (16px), while previews retain the code role.

**The Reading Measure Rule.** Keep documentation content to a maximum width of 75ch. Use normal prose wrapping and wrapped documentation code examples. Keep source and generated files horizontally scrollable where whitespace matters.

## Layout

The outer container has a maximum width of 1280px, centered with desktop padding (24px 32px). The workspace uses two equal columns with a gap (24px). Each panel has desktop padding (20px), aligned heading rows and coordinated source/output toolbars.

Above 800px, the source file toolbar has bottom margin (24px). The output toolbar has bottom padding (24px), with copy feedback positioned at its bottom. Preserve this clearance so feedback does not shift the editor/preview alignment. Empty feedback text stays hidden; structural toolbar clearance is separate from status visibility.

Between 801px and 1100px, pane headings can wrap into taller rows (100px). Source and output toolbars use matching minimum heights (112px). Output actions occupy two rows, with the ZIP action spanning both columns.

At 800px and below, stack workspace panels with a gap (20px). Reduce container padding (12px 18px), panel padding (16px), and editor/preview height from 320px to 240px. Output actions retain two rows. At 400px and below, reduce outer and panel padding further (10px 12px and 12px); stack form fields and let selectors fill the pane width.

Documentation uses a sidebar (240px), a flexible article column and a gap (40px). On phones, place search above a closed native Browse documentation disclosure. Keep Playground and Documentation links visible. Hide idle/loading search status text visually on phones while retaining its live status semantics. Show results and error feedback when applicable. This search treatment does not suppress conversion errors or copy feedback.

## Elevation & Depth

The system uses no shadows. Panel backgrounds, jade washes, hairline borders and the dark masthead establish hierarchy. Picker menus appear above nearby content through positioning and stacking order. The task and reading layouts currently use no decorative imagery or motion.

## Shapes

Use the frontmatter's control radius for buttons, fields, file surfaces and code blocks. Workspace panels have the larger panel radius. The masthead has its own radius and a smaller phone variant. Most dividers and borders are thin solid lines (1px). The empty preview uses a dashed border; active file dropping uses a dashed outline (3px, offset 4px).

## Components

### Actions

Copy file is the filled primary action. Download file follows it. The citation ZIP is a quiet text action, prepared only when requested. Templates download individually. Buttons, inputs, selectors, picker options, navigation links and disclosure summaries have a minimum height (44px). The frontmatter omits fixed heights because controls can grow with their contents. Hover uses wash and an accent border for secondary buttons. Primary hover darkens with brightness (.9). Disabled actions use reduced opacity (.5) and remain unavailable for stale results.

Every interactive control has visible keyboard focus (3px accent outline, offset 3px). Masthead focus uses the on-brand color. Preserve system colors in forced-colors mode. Code-copy icons have labelled targets (44px) and sit inside bordered code blocks.

### Fields and file pickers

Keep native labels and persistent short hints. Put technical version and licence help in native disclosures outside input hint descriptions. Invalid source text uses the notice border. Keep author identifiers on their author's row.

Source and output selectors use searchable comboboxes backed by native selects. Preserve grouping, name sorting, filename/group filtering and keyboard behavior. Mark package templates as incomplete. Keep optional name correction separate from export eligibility; structured names need no inferred-name disclosure. Open it only for potentially ambiguous inferred names. Names look right or closing the disclosure keeps it closed until the names change.

### Tabs and navigation

Selected entry and repository-use tabs use a wash, border and semibold accent text. Entry tabs activate manually because a change can await conversion. Keep focus and cursor position stable during refresh. Site navigation uses the masthead palette and `aria-current`. Documentation marks the current guide or parent visibly and preserves section anchors.

### Workspace panels and states

Keep the empty preview useful, with a short example invitation. Place output actions before the generated file. Use stable editor and preview heights. Show contextual notices below the finishing actions. Hide empty status elements. Announce meaningful loading, errors and completed actions without announcing each keystroke.

The draft and transfer rules follow [PRODUCT.md](PRODUCT.md): preserve unchanged source text, keep partial drafts editable, retain both drafts after failed transfer, reject stale async results and disable stale exports. Entry modes represent the same project metadata. Transfer through the same Python engine and use a CodeMeta working copy after form edits. Refresh valid edits automatically after a short pause. Prepare the converter in the background; active progress clears on invalid input. Keep genuine omissions and actionable errors visible. Suppress informational missing-field findings.

### Supporting content

Keep repository-use instructions visible with command-line, pre-commit and CI tabs. Field lookup remains a secondary disclosure with an initial search prompt. Search terms and paths together. Show matching formats in plain sections separated by hairlines. Keep unsupported mappings explicit and link the pinned source. Load lookup independently of conversion and preserve its search on retry.

Documentation renders existing Markdown and linked repository guides into local pages. Search links directly to sections and works without the converter. Keep article and guide navigation usable without JavaScript. Wrap long code examples. Place narrow-screen tables in labelled, keyboard-scrollable regions.

Keep accurate privacy copy and project/source/docs/accessibility/issues/licence links in the colophon. Preserve the project, linked author, first-publication year and DOI signature. [PRODUCT.md](PRODUCT.md) owns the browser-only processing and network constraints.

## Do's and Don'ts

### Do

- **Do** preserve aligned source/output toolbars and desktop feedback clearance.
- **Do** use semantic colors, minimum 44px control heights and visible keyboard focus.
- **Do** distinguish selected tabs, stale output and actionable notices in text as well as color.
- **Do** test empty, loading, parse-error, runtime-error, corrected and stale-result states in both themes and on phones.

### Don't

- **Don't** add decoration that obscures metadata, actions or guides.
- **Don't** use placeholders as instructions or hide errors with the phone search-status treatment.
- **Don't** move focus during automatic refresh or make name confirmation a condition of export.
- **Don't** turn the related project family into shared behavior or a shared stylesheet without checking each project's needs.

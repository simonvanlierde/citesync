# Accessibility

Last reviewed: 15 November 2026. Review this statement annually and before each release.

The playground and documentation support keyboard navigation, visible focus and labelled controls. They follow your system's light or dark theme until you choose one with the sun/moon button in the footer. The button's label names the theme it will switch to. Your choice is remembered when browser storage is available; without JavaScript, the site follows your system theme.
Use the skip link at the start of each page to reach its main content.

## Use the playground

Use Tab to move between controls. In a file selector, type to filter filenames, use the arrow keys to choose an option and press Enter to select it. Escape closes the list.
The entry tabs use arrow keys to move focus and Enter or Space to switch views.

Loading messages and errors use status announcements. Exports are disabled while a result is stale or invalid.
The playground needs JavaScript, WebAssembly and a network connection to load the converter.

## Read the documentation

Guides and their navigation work without JavaScript. Full-text search needs JavaScript.
On a narrow screen, open **Browse documentation** to choose a guide.
Wide reference tables scroll horizontally; focus a table's scrollable region to use the arrow keys.

## Checks and limitations

Automated browser checks cover Chromium, Firefox and WebKit, keyboard interactions, narrow screens, light and dark themes, and selected axe accessibility rules.
These checks do not establish WCAG conformance or replace testing with assistive technology.
Physical iPhone/Safari and screen-reader checks remain part of release verification.

If the playground does not work for you, use the [command-line installation instructions](getting-started.md).
To [report an accessibility problem](https://github.com/simonvanlierde/citesync/issues), include the page, the task you were trying to complete, and your browser or assistive technology.

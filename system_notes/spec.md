# System notes renderer — spec

## Goal

Render a partnership's system notes into three outputs from one source:

- a self-contained HTML page that reads well on any screen
- a two-column US-letter PDF whose cross-references and table of contents carry
  page numbers
- a plain-text rendering for pasting sections into email

The notes are a long, deeply structured bidding and carding agreement written in
Pandoc Markdown. The tool is a renderer only: it knows how bids, suits, and
shorthand are written, but nothing about what they mean.

## Inputs and repository layout

- **Input**: one `notes.md` per partnership, in Pandoc Markdown plus this tool's
  small notation: bids written plainly (`4S`, `2NT`), `!S !H !D !C` for suits
  outside bids, and `[](#section-id)` for cross-references. A YAML block at the
  top carries the title (required) and an optional date.
- **Real notes** are private partnership agreements, so they live in
  `bridge-private` rather than in this public `bridge` repo, which holds only
  the tool and a fixture. In `bridge-private`, each partnership has a
  `system_notes/<partner>/` directory holding its `notes.md`, the committed
  outputs, and a `regenerate.sh` wrapper that runs this tool from a `bridge`
  checkout beside `bridge-private`.
- **The fixture** (`fixture/notes.md`) is AI-drafted sample material written to
  exercise the notation — five-deep lists, forward and backward references,
  suits in headings and prose. It pairs a conventional 2/1 outline written in
  prose with one maximal-shorthand section holding no subsections (a Woolsey
  defense to 1NT) that stress-tests how much a page of nested bullets can carry.
  It must say prominently, in its own text, that no human has reviewed or
  verified any of it.
- **Sibling tool**: `convention_cards/` likewise keeps its tool in this repo and
  its private data in `bridge-private`. This tool copies the `regenerate.sh`
  wrapper convention from `convention_cards/` rather than sharing code with it.

## Core design: one source, one HTML document for screen and print

Pandoc, extended by this tool's Lua filters, turns the Markdown into a single
HTML document with the tool's stylesheet embedded. A browser shows that HTML
directly. WeasyPrint lays the same HTML out under the stylesheet's
`@media print` rules to make the PDF. The plain-text rendering bypasses the
HTML: pandoc's plain-text writer produces it from the same source and filters.

Rationale for Markdown over the alternatives considered:

- **LaTeX** has the best print machinery but the heaviest source, and no good
  route to an HTML page that reads well on any screen.
- **Typst** has a light syntax and native page references, but its HTML export
  is still experimental (as of version 0.15, mid-2026) — too unsettled a base
  for the screen rendering.
- **AsciiDoc** has native cross-references and a book-oriented vocabulary, but
  its styling is a theme rather than arbitrary CSS, and page-numbered references
  need its browser-based PDF path.
- **Hand-written HTML** makes deeply nested lists unreadable in the source.

Markdown has the lightest, most legible source, and pandoc's Lua filters add
this tool's notation cheaply: they rewrite the parsed document, so the Markdown
syntax itself needs no extension.

Rationale for WeasyPrint as the print engine: it implements the CSS paged-media
features the print layout depends on, with no browser in the loop. Those
features are `@page` margin boxes, running headers via `string-set`,
multi-column flow, and `target-counter()` for page-numbered references. A
prototype confirmed that every reference resolved correctly, including backward
references and targets inside nested list items set in two columns. If
WeasyPrint ever regresses, the fallback is Paged.js, a JavaScript implementation
of the same CSS features, run inside Chromium. Paged.js rendered the prototype
equally well but is not the default, because it needs Playwright to drive the
browser. It also needs the stylesheet embedded, as the renderer already writes
it: in the prototype, Paged.js failed to load a linked stylesheet from a page
opened as a local file.

## Appearance {#appearance}

One stylesheet, shipped with the tool, holding `@media screen` and
`@media print` blocks. There is no per-partnership override: the layout and
colors are the tool's, and flexibility is added only when a second partnership
wants something different.

- **Typeface**: IBM Plex Serif for body and headings, 11pt body in print. Chosen
  from full-document renders of the fixture across open-licensed candidates: the
  serif scanned best when skimming list-heavy pages, and Plex Serif meets the
  letterform preferences the search settled on — a straight-tailed Q with no
  flourish, a simple `g`, a conventional ampersand, an undecorated zero, true
  italics, and a distinguishable `I l 1`. Inter and Open Sans are the recorded
  sans-serif fallbacks; both rendered well and either could take over if a serif
  proves wrong on paper. Further serif candidates are queued in `tasks.md`
  #serif-alternatives.
- **Fonts are installed, not bundled.** The stylesheet names families,
  WeasyPrint finds them through fontconfig, and the README documents the
  install. Only publicly available, open-licensed fonts are used, so any machine
  can be set up identically; the exact files are captured in `bridge-private`
  alongside its other fonts, in case an upstream copy vanishes or drifts. The
  public repo carries no font files.
- **Screen**: a single column of readable measure that narrows with the
  viewport.
- **Print**: US letter paper size; running document title and section title in
  the page header, "page / total" in the footer.

## Command line

`python -m system_notes.render_notes notes.md` — one positional input;
`notes.html`, `notes.pdf`, and `notes.txt` are written beside it, named after
the input. The outputs are committed alongside the source in `bridge-private`,
so the latest notes can be read from the repository on any device without a
build, and so the self-contained HTML can be published anywhere later. Where it
is published is undecided and not needed soon.

Pandoc runs with `--fail-if-warnings`, so a duplicate heading id or similar
authoring slip stops the render rather than producing a subtly wrong document;
the filters add their own hard errors for a missing title. WeasyPrint gets the
same treatment for the same reason: it warns about a stylesheet it cannot parse
or a layout it cannot honor, then lays the page out anyway, so its warnings fail
the render too. One is exempt — the phone-width screen media query, which it
cannot parse and does not need.

## Testing

- **Filter unit tests** run pandoc over small Markdown snippets with one filter
  at a time and assert the resulting HTML and plain text.
- **Golden files** {#goldens} for the fixture, committed and diffed on every
  test run: the HTML, the plain text, and the PDF as extracted by
  `pdftotext -layout`. The PDF golden is text rather than bytes because the
  bytes embed font subsets and vary with font-file and WeasyPrint versions, and
  a binary diff says nothing about what changed; the extracted text carries page
  numbers, running headers, and column order, and diffs like any file. It is
  stable as long as the same fonts are installed. Rasterized image diffs are a
  possible later addition for reviewing layout changes; the design does not
  depend on them.

The tests need every program and font the tool itself needs, since they render
the fixture for real. `Brewfile` lists them, each with what it is for, and the
README gives the install command.

## Module shape

- `render_notes.py` — the command line; runs pandoc twice, as a command, and
  WeasyPrint once, through its Python API.
- `filters/` — one Lua filter to a job: a check, a notation rule, or a
  structural rewrite.
- `template.html` — a minimal skeleton replacing pandoc's default, so none of
  pandoc's default styling reaches the print layout.
- `notes.css` — the stylesheet.
- `pdf_inspection.py` — the PDF readouts the tests share: extracted text.
- `fixture/notes.md` and `fixture/golden/` — the sample document and its
  expected renderings.
- `filters_test.py`, `render_notes_test.py` — the tests above, beside the code
  they cover per the repo's `*_test.py` convention; `update_goldens.py`
  refreshes the goldens.

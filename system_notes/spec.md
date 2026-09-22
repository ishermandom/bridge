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

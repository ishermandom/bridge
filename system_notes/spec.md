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
directly. For the PDF, the renderer first packs the HTML's sections onto
explicit page and column boxes; #section-packing records why. WeasyPrint then
lays the packed HTML out under the stylesheet's `@media print` rules. The
plain-text rendering bypasses the HTML: pandoc's plain-text writer produces it
from the same source and filters.

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

## Notation {#notation}

The notation is deliberately tiny — each piece a Lua filter over pandoc's
document tree — because every addition is syntax the author must remember and
syntax the plain-text output must survive:

- **Bids and suits**: a bid is written plainly — `4S`, `2NT` — and detected: a
  level 1–7 and a strain standing as a word of its own, so `1ST` and `15S` are
  left alone. Notrump is always `NT`; any other spelling after a level — `2N`,
  `2n`, `2nt` — is a hard error (`bids.lua` says why). `!S !H !D !C` mark a suit
  outside a bid. Either way the source stays plain ASCII and reads naturally in
  an auction (`1S – 2C`). Each strain becomes a span; suits are colored
  four-color style. The plain-text rendering keeps bids exactly as typed and
  reduces `!H` to its letter — in email, the letters read better than symbols.
- **The major-suit placeholder is bolded**: the `M` closing a placeholder
  compound — `OM`, `W2M`, `4cM`, `4+OM` — is set strong, so the placeholder
  stands out from the capitals around it. Compounds are written apart
  (`4cM & 5+m`) rather than run together, which keeps `+` meaning "or more"
  alone and leaves every placeholder at the end of its own word, where the
  filter looks for it. Ordinary capitals ending in `M` (`BAM`) and the lowercase
  minor placeholder `m` stay plain; the filter's header carries the exact
  grammar. The plain-text rendering keeps shorthand exactly as typed.
- **Cross-references**: a link to a heading — `[Stayman](#stayman)` — is classed
  `xref` and set in italic, the way prose marks a term of art; print CSS appends
  "(p. N)" to every one, since a reference on paper is worth nothing without the
  page. Sections are unnumbered — the notes are read by section name, and a
  number would only add noise — so a reference cites the name rather than a
  number. Left empty, as `[](#stayman)`, a link takes the section's title for
  its text, which saves keeping a second copy of the title in step with the
  heading; the author who wants a shorter name writes it out instead. On paper
  the link keeps its color, which marks the text as pointing elsewhere even
  where it cannot be followed. An unknown target is a hard error, so a typo
  cannot ship as a dead link. Which links deserve a page number is unsettled —
  `tasks.md` #numbered-references.
- **Unbreakable tokens**: card-count ranges like `15–17` and slashed shorthand
  like `P/C` are wrapped so they never break across a line. The author writes
  them plainly; the filter recognizes digits–dash–digits, and a slashed word
  holding a capital or a digit (so `and/or` stays prose). Whole auctions may
  still break at a column edge; keeping them intact is deferred until a real
  page shows a bad break.

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
- **Suits**: a dedicated face on the `.suit` span carries them, never the body
  font — Plex Serif has no suit glyphs, and most text faces do not, so leaving
  them to fallback means accepting whatever fontconfig finds. They are colored
  four-color style — spade black, heart red, diamond orange, club green — and
  set slightly larger than the text so the glyphs match the digits they follow,
  at regular weight (the stylesheet carries the why). Inside italic text a suit
  leans with the letters, through an explicit skew the stylesheet owns; a
  coupling test holds the angle to the installed body italic's. The face is STIX
  Two Math, chosen over the prototype's Source Sans 3 and other verified
  carriers (Noto Sans Symbols 2, Overpass, DejaVu Sans) by glyph measurement and
  an 11pt specimen: its four suits are uniformly wider than Source Sans 3's
  tall-and-narrow set at the same height, where the others improved only some
  suits, ran small, or carried wide side bearings. It also ships with macOS and
  pairs naturally with serif text.
- **Fonts are installed, not bundled.** The stylesheet names families,
  WeasyPrint finds them through fontconfig, and the README documents the
  install. Only publicly available, open-licensed fonts are used, so any machine
  can be set up identically; the exact files are captured in `bridge-private`
  alongside its other fonts, in case an upstream copy vanishes or drifts. The
  public repo carries no font files.
- **No font fallback goes unnoticed.** Every render inspects the PDF's embedded
  fonts and fails if a family outside the chosen set appears — the sign that
  something fell back to whatever fontconfig found: a glyph the chosen fonts
  lack, or an element the stylesheet gives no family. The check is also why the
  stylesheet names no monospace face. No code span has appeared in the notes so
  far, and the first one will fail the render rather than quietly pick up the
  machine's monospace; a face gets chosen then.
- **Heading rank without a size ladder**: the section heading takes the accent
  color and italic; below it, subsections and their children stay at body size
  and are told apart by underline and weight. The notes nest too deeply for each
  level to claim a size of its own.
- **A marker per list depth, paired by round of the auction**
  (`○ ● □ ■ △ ▲ ▷ ▶ ▽ ▼ ◦ •`): the two depths of one round share a shape, the
  unfilled marker for the seat that calls first and the filled one for the seat
  that answers, so a line's shape says which round it belongs to and its fill
  says which seat. The full-size shapes take the first five rounds and the two
  small bullets close the ladder, so markers lose prominence only past the
  depths real outlines use; the right-pointing pair sits between the upward and
  downward pairs, keeping those mirror images apart. The ladder runs six rounds
  deep, past anything a real outline reaches; a deeper list repeats the last
  marker, since CSS cannot count nesting depth and the stylesheet's deepest
  selector matches everything below it. The markers are explicit glyphs, checked
  against Source Sans 3's coverage, never the disc/circle/square keywords:
  browsers draw the keywords as shapes while WeasyPrint substitutes glyphs of
  its own choosing, and the two media would drift apart.
- **Suit bids align on their own; notrump does not.** Plex's digits are tabular
  by default and STIX's four suits share one advance width, so every suit bid
  comes out the same width with no styling at all, and a run of list items
  opening with one lines up. `NT` is two letters where a suit is one symbol, so
  a notrump bid is wider, and calls like `Pass` and `Dbl` wider still. An
  earlier design boxed every strain to a fixed width to bring those into line
  too: `NT` cannot be squeezed into a suit's width, so the box has to take
  `NT`'s, which opens a gap after every suit symbol — a worse trade than letting
  the one bid stand out. A fallback face with proportional digits would need
  `tnum`, and then only on bids, never body-wide: Inter's `tnum` also widens the
  hyphen, and tabular digits in prose spread shape notation like `5-3-3-2`
  apart.
- **Screen**: a single column of readable measure that narrows with the
  viewport; the table of contents at the top; cross-references as links.
- **Print**: US letter paper size; running document title and section title in
  the page header, "page / total" in the footer; a page-numbered table of
  contents listing only the top-level sections, packed like any section
  (#section-packing); every cross-reference followed by its page number.
- **A printed section is an atom.** {#section-packing} It renders whole on one
  page where it fits, ideally within a single column. The two columns exist so
  that short sections can sit side by side. A section taller than a column gets
  a page of its own: its heading spans the page and its body flows in two
  columns beneath, continuing onto further pages when even that page cannot hold
  it; `tasks.md` #wide-overflow asks whether such a section should instead fail
  the render. Once a page can take no more, its sections are rebalanced between
  the two columns, so the two come out near the same height rather than filling
  the first to the brim and leaving the second bare.
  - CSS cannot express this fitting in any engine — no multicol does page-level
    fitting of column-spanning atoms — and WeasyPrint additionally ignores break
    properties on a multicol's children and pushes a fragmenting multicol
    container to a fresh page. So the renderer packs sections itself, from a
    measuring probe render; `print_layout.py` carries the mechanism.
  - `column-span: all` is never used: with a spanning heading inside one
    document-wide column flow, WeasyPrint silently dropped everything after the
    first section in one render (12pt body; the exact trigger was not isolated).
  - The section wrappers the packer keys on are raw markup rather than pandoc
    divs; `sections.lua`'s header says why.
  - The packer works on a parsed document rather than on the markup text, and
    parses with `tinyhtml5`, the parser WeasyPrint itself uses — so no second
    reading of the markup can disagree with the reading that gets laid out.

## Command line

`python -m system_notes.render_notes notes.md` — one positional input;
`notes.html`, `notes.pdf`, and `notes.txt` are written beside it, named after
the input. The outputs are committed alongside the source in `bridge-private`,
so the latest notes can be read from the repository on any device without a
build, and so the self-contained HTML can be published anywhere later. Where it
is published is undecided and not needed soon.

Pandoc runs with `--fail-if-warnings`, so a duplicate heading id or similar
authoring slip stops the render rather than producing a subtly wrong document;
the filters add their own hard errors for a missing title, a skipped heading
level, and a link to a heading that does not exist. WeasyPrint gets the same
treatment for the same reason: it warns about a stylesheet it cannot parse or a
layout it cannot honor, then lays the page out anyway, so its warnings fail the
render too. One is exempt — the phone-width screen media query, which it cannot
parse and does not need.

## Testing

- **Filter unit tests** run pandoc over small Markdown snippets with one filter
  at a time and assert the resulting HTML and plain text.
- **Packer unit tests** drive `print_layout.py`'s packing on hand-built lists of
  section heights, and `paged_document` on hand-built markup, with chosen
  heights standing in for the measuring render so that no render runs.
- **Golden files** {#goldens} for the fixture, committed and diffed on every
  test run: the HTML, the plain text, and the PDF as extracted by
  `pdftotext -layout`. The PDF golden is text rather than bytes because the
  bytes embed font subsets and vary with font-file and WeasyPrint versions, and
  a binary diff says nothing about what changed; the extracted text carries page
  numbers, running headers, and column order, and diffs like any file. It is
  stable as long as the same fonts are installed, which the next test enforces.
  Rasterized image diffs are a possible later addition for reviewing layout
  changes; the design does not depend on them.
- **An embedded-font test** asserts that the fixture PDF embeds exactly the
  chosen families, and that a document forcing a fallback (a code span) fails to
  render. A fallback is otherwise invisible: the prototype once picked up
  Georgia for a single character. On a machine without the fonts the render
  fails loudly rather than writing a plausible wrong golden, which is what an
  eventual CI run needs.
- **A page-reference test** enumerates the cross-references from the rendered
  HTML and checks each one's printed "(p. N)" against the page its heading
  actually lands on, read from the PDF's bookmarks — WeasyPrint writes one per
  heading, with the exact page. The golden shows a page number is unchanged;
  this shows it is correct.

The tests need every program and font the tool itself needs, since they render
the fixture for real. `Brewfile` lists them, each with what it is for, and the
README gives the install command. pypdf, which reads the bookmarks, is a
test-only Python dependency.

## Module shape

- `render_notes.py` — the command line; runs pandoc twice, as a command, and
  WeasyPrint once, through its Python API.
- `filters/` — one Lua filter to a job: a check, a notation rule, or a
  structural rewrite.
- `template.html` — a minimal skeleton replacing pandoc's default, so none of
  pandoc's default styling reaches the print layout.
- `notes.css` — the stylesheet.
- `print_layout.py` — the section packer: it measures a probe render and
  rewrites the HTML into explicit page and column boxes (#section-packing
  records why).
- `pdf_inspection.py` — the PDF readouts the renderer, the packer, and the tests
  share: embedded fonts, per-page text heights, bookmark pages, extracted text.
- `fixture/notes.md` and `fixture/golden/` — the sample document and its
  expected renderings.
- `filters_test.py`, `print_layout_test.py`, `render_notes_test.py` — the tests
  above, beside the code they cover per the repo's `*_test.py` convention;
  `update_goldens.py` refreshes the goldens.

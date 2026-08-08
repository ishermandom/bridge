# ACBL convention card renderer — spec

## Goal

Turn a convention card JSON file into a print-ready PDF that is pixel-identical
to the official ACBL card everywhere except the entered content, which is
typeset in a swappable custom font with automatic fitting to the available
space. The tool is a renderer only: cards are authored elsewhere and arrive as
JSON, and the field vocabulary grows incrementally rather than launching
complete.

## Inputs and neighbors

- **Input**: a card JSON file — `{"settings": {<section>: {<key>: <value>}}}`,
  where each value is `"on"` (a checkbox), free text that may contain
  `!c !d !h !s` suit markup, or a number (which card of a printed holding to
  circle on the lead charts). The schema is pinned to the Bridgodex export
  format — cards can be authored on Bridgodex and exported — and Bridgodex
  publishes no schema document, so the vocabulary is reverse-engineered and
  grows key by key.
- Real exports carry names and ACBL member numbers, so they live in
  `bridge-private`; fixtures in this repo use placeholder data only.
- **Base artwork**: `convention_cards/data/acbl.pdf` — the official fillable
  ACBL card: one page, 576×612 pt (8″ × 8.5″), 433 form fields (148 text fields,
  207 checkboxes, 78 grouping nodes).
- **Sibling tool**: `convention_cards/make_card.py` merges a finished card PDF
  with a reminders strip. Its geometry is tuned to letter-size BridgeWinners
  exports, so this renderer's 8″ × 8.5″ output is not a valid input to it today;
  integrating the two is deferred as a nice-to-have. Until then the two tools
  stay independent.

## Core design: overlay on the original, never re-typeset

The output PDF keeps the original `acbl.pdf` page as its base layer,
byte-for-byte, and merges a transparent overlay carrying only the entered
content. Rationale: the card's printed artwork embeds ten subset fonts and a
layout engine's worth of micro-decisions; re-typesetting it (in TeX, HTML,
Typst, or anything else) can approach the original but never reach a zero pixel
diff. Reusing the page is pixel-perfect by construction and survives future ACBL
revisions by swapping the base file.

- **Overlay**: drawn with `reportlab` (which embeds the custom font and exposes
  exact glyph widths), merged with `pypdf` — the same stack `make_card.py`
  already uses.
- **The form fields are a geometry database, not a filling mechanism.** Each
  field supplies its name, rectangle, default font size (from its `/DA` string),
  and multiline flag (from `/Ff`). We never fill fields: form appearance is
  viewer-dependent, locked to Arial, and offers no real wrap, shrink, or font
  control.
- The output strips the form dictionary and all widget annotations, so it prints
  as a plain document. Blank widgets draw no border or background, so stripping
  them leaves exactly the printed blank card.

## Vocabulary

A mapping table from JSON `(section, key)` to an ACBL field name plus a
rendering policy — text entry, checkbox mark, or lead-chart circle. The table is
the single place a key's meaning is recorded.

**Unknown input is a hard error**: an unrecognized section or key, a value that
doesn't match its field's policy (e.g. text where a checkbox is expected), or
unknown `!x` markup all fail the run. Rationale: a printed card must never be
silently missing content the JSON asked for. Consequence accepted: while the
vocabulary is incomplete, inputs must be trimmed to the mapped keys. The
export's top-level `notes` field gets the same treatment: the one-page card has
no home for it, so a non-empty `notes` fails the run rather than dropping
content silently, while an empty `notes` is tolerated.

## Text fitting

Per text entry: start at the field's own default font size (read from the form),
lay out on one line — or wrap, when the form marks the field multiline — and
shrink by search until the text fits the rectangle, down to a configurable size
floor. Text that cannot fit at the floor raises an error naming the field, the
text, and the overflow amount. Glyph metrics come from the embedded font, so
fitting is a deterministic pure function of (text, font, rectangle) —
unit-testable with no rendering involved.

## Appearance

- **Entry color**: configurable; default dark blue, distinguishing entries from
  the card's black-and-red print.
- **Font**: swappable input (a font file path); the default is a placeholder
  face set in code (see `tasks.md` for the intended end state), revisited once
  rendered samples inform a final pick. Fonts are not committed to the repo, so
  a missing font is a hard error naming the path that was tried. Open detail:
  the text font may lack suit-symbol glyphs — fall back to a dedicated symbol
  font or drawn paths if so.
- **Checkboxes**: an X drawn across the field's rectangle in the entry color.
- **Suit symbols**: four-color — ♥ red, ♦ orange, ♠ blue, ♣ green — configurable
  alongside the entry color.
- **Lead-chart circles**: an ellipse in the entry color around the printed card
  character. Those characters are base artwork, not form fields, so their
  coordinates must be measured by hand when the lead-chart vocabulary entries
  land.

## Command line

`render_card.py INPUT.json OUTPUT.pdf`, positional like `make_card.py`, plus
`--font`, `--color`, and `--size-floor` options with the defaults above.

The tool reports every field whose text had to shrink below the field's default
size, naming the field and the sizes involved — the card still renders, but the
report shows the user where content is pushing the limits.

## Testing

- **Blank-card golden**: rasterize the renderer's output for an empty input and
  the original `acbl.pdf` at a fixed DPI; require a zero pixel diff. If
  annotation rendering makes the comparison unfair, compare against the original
  with annotations stripped — the printed artwork is the target.
- **Filled-card goldens**: committed rasters of representative placeholder
  cards, regenerated when the vocabulary or font changes (churn accepted for the
  regression coverage). Because fonts live outside the repo, these goldens
  reproduce only on a machine with the same font files installed.
- **Unit tests**: the fitting engine, suit markup parsing, and vocabulary
  validation.
- **Rasterizer**: `pypdfium2`, pinned. A new dependency — nothing in the repo
  rasterizes PDFs today, and neither `pypdf` nor `reportlab` can render pixels.
  `pypdfium2` wheels bundle the PDFium renderer, so a pinned version produces
  identical rasters on every machine — unlike `pdf2image`, which shells out to
  whatever poppler the system has — and its license is permissive, unlike AGPL
  `PyMuPDF`.

## Module shape

Planned split, one module per concern: geometry (field data out of the PDF),
vocabulary (the mapping table), markup (suit symbols), fitting, overlay drawing,
and the CLI entry point.

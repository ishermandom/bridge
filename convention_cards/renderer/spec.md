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
- **Base artwork**: the official fillable ACBL card — one page, 576×612 pt (8″ ×
  8.5″), 433 form fields (148 text fields, 207 checkboxes, and 78 parent entries
  that only group other fields). The file lives in the private sibling repo, at
  `bridge-private/convention_cards/acbl.pdf`, so this public repo never
  redistributes ACBL's copyrighted form; `private_paths.py` finds the file at
  run time.
- **Sibling tool**: `convention_cards/make_card.py` merges a finished card PDF
  with a reminders strip. Its geometry is tuned to letter-size BridgeWinners
  exports, so this renderer's 8″ × 8.5″ output is not a valid input to it today;
  integrating the two is deferred as a nice-to-have. Until then the two tools
  stay independent.
- **Consumer**: `convention_cards/renderer/make_two_sided_card.py` renders a
  card JSON through this renderer onto the front of a two-sided print sheet,
  which one straight cut trims to size; the back is converted from a hand-built
  HTML card. The script's module docstring describes the sheet's layout.

## Core design: overlay on the original, never re-typeset

The output PDF keeps the original `acbl.pdf` page as its base layer,
byte-for-byte, and merges a transparent overlay carrying only the entered
content. Rationale: the card's printed artwork embeds ten subset fonts and a
layout engine's worth of micro-decisions; re-typesetting it (in TeX, HTML,
Typst, or anything else) can approach the original but never reach a zero pixel
diff. Reusing the page is pixel-perfect by construction and survives future ACBL
revisions by swapping the base file.

- **Overlay**: drawn with `reportlab` (which embeds the custom font and exposes
  exact glyph widths), placed with `pypdf` — the same stack `make_card.py`
  already uses. The overlay joins the page as a form XObject
  (`render_card._draw_overlay`) rather than through `pypdf`'s page merge. The
  merge rewrites the overlay's drawing instructions into the page's own: it
  parses them to clip them and to rename any resource names that clash with the
  page's, then stores them uncompressed. A form XObject needs none of that.
- **The form fields are a geometry database, not a filling mechanism.** Each
  field supplies its name, rectangle, and default font size (read from the
  field's default-appearance string, `/DA`). We never fill fields: how a filled
  field looks depends on the viewer, its text is locked to Arial, and the form
  offers no real control over wrapping, shrinking, or font.
- The output strips the form dictionary and all widget annotations, so it prints
  as a plain document. Blank widgets draw no border or background, so stripping
  them leaves exactly the printed blank card.

## Vocabulary {#vocabulary}

The vocabulary is a mapping table, in `vocabulary.py`, from each JSON
`(section, key)` to its target on the card: a text field to write in, a checkbox
to mark, or a printed card in a lead chart to circle. The table is the single
place a key's meaning is recorded.

**Unknown input is a hard error**: an unrecognized section or key, a value that
doesn't suit its target (e.g. text where a checkbox is expected), or a `!`
followed by any letter but c, d, h, or s all fail the run. Rationale: a printed
card must never be silently missing content the JSON asked for. Consequence
accepted: while the vocabulary is incomplete, inputs must be trimmed to the
mapped keys.

The export also carries a top-level `notes` field beside `settings`, and the
one-page card has no home for it. An empty `notes` is fine; a non-empty one
fails the run rather than silently dropping its content.

## Text fitting

Each text entry first tries one line at its field's default font size, read from
the form. When that overflows, the fitter looks for the largest font size at
which the text fits the field, either on one line or word-wrapped onto more. The
size never drops below a configurable floor, whose default is
`DEFAULT_SIZE_FLOOR` in `overlay.py`. Wrapped lines must fit within the field's
height plus a small upward bleed into the gap between the card's ruled rows: the
bottom line sits where a one-line entry would, and extra lines stack above it,
the way a person squeezes a second line in above the rule. Line breaks happen
only at spaces, so suit symbols never separate from their neighboring text.

An entry that cannot fit even wrapped at the floor is a hard error naming the
field and text. Bridgodex's own renderer instead sends overflow to footnotes on
a second page; footnotes were considered and declined. At the default floor, two
wrapped lines don't fit a standard-height blank even with the bleed, so in
practice only the card's taller fields wrap. We accept that limit rather than
exempt wrapped entries from the floor.

Beside a few fields' printed blanks, the card is genuinely empty — an
inter-panel gutter to the right, an open band above — so the form's rectangles
understate the room an entry can really use. Those fields get extra room beyond
their rectangles (`FIELD_EXPANSIONS` in `overlay.py`), measured from the blank
card's artwork rather than any one card's entries, so the amounts hold for every
card. Special-casing individual fields this way is a deliberate choice: the
card's actual layout is the constraint that matters, and a handful of measured
exceptions beats any uniform rule, which could only be as generous as the most
crowded field allows and would leave this room unused.

The right column is the one group of exceptions large enough to describe by
position instead of by list: every blank there stops ~4pt short of the card's
outer border with nothing printed in between, so entries in fields ending near
that edge may run to just shy of the border (constants in `overlay.py`).

When an entry runs past the end of a gutter-expanded blank's printed underline,
the renderer continues the underline beneath it. Aligned blanks form a family
whose underlines extend together, so the rows keep one shared right edge. The
right column's underlines are not extended, since its entries overhang them by
only ~4pt. The mechanism and measured values live with `overlay.py`'s
rule-extension constants.

Glyph metrics come from the embedded font, so fitting is a deterministic pure
function of (text, font, rectangle) — unit-testable with no rendering involved.

## Appearance {#appearance}

- **Entry color**: configurable; default black. The cards are usually printed in
  black and white, where a colored entry prints as a lighter gray. Black is
  higher contrast, which improves legibility, especially for aging eyes. Even in
  black, the entries still stand out from the card's built-in print, because the
  font differs.
- **Font**: a swappable input (a font file path).
  - Default: a static version of Google Sans Flex, set for the card's
    conditions: 6pt optical size, SuperCondensed width, and Regular weight with
    its grade raised to match Medium's stroke. Grade is a font axis that
    thickens strokes without widening the letters.
  - Rationale: print tests settled on Medium's stroke thickness. Of the fonts
    tested, this version is the narrowest that keeps both the tallest lowercase
    and Medium's stroke; the narrower candidates have shorter lowercase and
    thinner strokes. Raising the grade instead of the weight is what gives it
    Medium's stroke at Regular's width. Measurements and provenance live in
    bridge-private's `convention_cards/fonts/README.md`.
  - Optical size: a font axis that reshapes letters for the size they print at;
    small settings give up large-size refinement for the taller lowercase and
    sturdier strokes small print needs. 6pt is the axis's minimum, not the size
    entries print at — every entry on the card falls in that small-print range.
  - Fallback: if the pick proves unworkable in practice, Roboto Condensed
    Medium, the runner-up on the same measurements.
  - Location: fonts are not committed to this repo. The default lives in
    bridge-private and is found at run time, like the base artwork, so a missing
    font is a hard error naming the path that was tried.
- **Vertical placement** {#vertical-placement}: an entry's baseline sits just
  above its printed rule — about 1pt of daylight — the way a hand writes on a
  line, with descenders crossing the rule. Two alternatives were rejected:
  centering the glyph box in the field's rectangle floats entries awkwardly far
  above the line, and a baseline directly on the rule reads as merged with it.
- **Checkboxes**: an X drawn across the field's rectangle in the entry color.
- **Suit symbols**: four-color — ♠ blue, ♡ red, ♢ amber, ♣ green — configurable
  through `render_card`'s `palette` argument; only the entry color has a
  command-line option.
  - Tones: the "gentle" palette — near-equal perceived lightness (CIE L\*
    42–53), so no suit fades ahead of the others when the card prints in black
    and white. The exploration that produced it, with every alternative
    considered, lives in `palette_specimen.py`.
  - Shapes: the heart and diamond print open, with thickened outlines, so
    open-versus-filled marks the red suits. Monochrome card printing has long
    drawn the red suits open and the black suits filled, and Unicode's first
    four suit characters (♠ ♡ ♢ ♣, U+2660–2663) follow the same scheme, so the
    treatment reads as learned convention, not invention. The spade and heart
    share a near-identical blob shape, so once color is gone, open-versus-filled
    is what tells them apart at a glance; the diamond opens to match the heart,
    since the red suits read as a pair and opening just one of them would be
    inconsistent. The club and spade both stay filled, kept apart by silhouette
    — the club's lobed edge against the spade's smooth one — and opening a black
    suit to separate them further would break the red/black code. The diamond's
    outline is thickened by 9% of the symbol size, the heart's by 8%: the
    diamond's shorter perimeter deposits less ink, so the extra weight evens the
    pair.
  - Size: suit glyphs come from Apple Symbols, which draws them only x-height
    tall; the renderer enlarges them to stand cap-height tall beside the text.
  - Width: all four suits share one advance width, the heart's, since the heart
    is the widest glyph; narrower glyphs stretch horizontally to fill it, so
    text following a symbol aligns across stacked rows without extra side space
    around the slimmer suits. Centering unstretched glyphs in the shared width
    was rejected: the daylight around the naturally narrow diamond read as a gap
    in the text.
- **Lead-chart rings**: a numeric JSON value picks which printed card to ring,
  counting from 1 at the left.
  - Shape: a rectangle with generously rounded corners, in the entry color,
    around the printed card character. Many ringed characters are x's, the
    chart's stand-in for a low card, so the corners must be round enough to read
    as a hand-drawn circling rather than a checkbox marked with an X. A true
    ellipse was rejected: in the ~2pt between neighboring chart cards, an
    ellipse tight enough to fit crosses its own glyph's corners.
  - Padding: the chart spaces its characters unevenly, so full padding would
    crowd some rings against a neighbor. Each ring instead pads both sides by
    only what its tighter side allows (constants in `overlay.py`), so the glyph
    always sits exactly centered. Centering the glyph outranks evening out the
    daylight around the ring: a ring shifted off-center reads as missing its
    target, while uneven gaps just reflect the artwork's own spacing.
  - Positions: the ringed characters are base artwork, not form fields, so their
    boxes were measured once from the PDF's own text layer (pypdfium2's
    character-level API) and are recorded in `lead_charts.py`.

## Command line

Run from `convention_cards/` (see #module-shape):

```sh
python3 -m renderer.render_card INPUT.json OUTPUT.pdf
```

The input and output paths are positional, as in `make_card.py`. The `--font`,
`--color`, and `--size-floor` options override the defaults above.

The tool reports every field whose text had to shrink below the field's default
size, naming the field, its default and fitted sizes, and how many lines the
text wrapped onto — the card still renders, but the report shows the user where
content is pushing the limits.

## Testing {#testing}

- **Blank-card golden**: rasterize two PDFs — the original `acbl.pdf` and the
  renderer's output for an empty input — and require a zero pixel diff. The
  rasterizer draws with form widgets off, so the original's fillable fields stay
  hidden and both images show only the printed artwork, which is what the
  renderer must reproduce.
- **Filled-card goldens**: committed rasters of representative placeholder
  cards, regenerated when the vocabulary or font changes (churn accepted for the
  regression coverage). Because fonts live outside the repo, these goldens
  reproduce only on a machine with the same font files installed.
- **Golden resolution** {#golden-resolution}: both whole-card comparisons
  rasterize at the filled goldens' scale, `GOLDEN_SCALE` in
  `regenerate_goldens.py`. Resolution matters for one kind of change: text
  moving straight up or down. An exact pixel comparison notices other changes
  far smaller than a pixel at any resolution — anti-aliasing turns a drawn
  shape's slightest shift into changed edge pixels, so shifting the card's
  artwork by 0.001pt shows even at 72 dpi, and text moving sideways shows within
  a twentieth of a point. But PDFium appears to set glyphs on whole pixel rows,
  so a line of text can move vertically by nearly a pixel unnoticed, depending
  on where its baseline falls within a row. The figures below come from moving
  one line of text in 0.025pt steps from ten starting positions.
  - **Precision needed**: about half a point. The finest vertical detail the
    design depends on is the 1pt of daylight between an entry's baseline and its
    rule (see #vertical-placement). A drift of half a point eats half that gap
    and starts to undo the placement; a quarter point, under a tenth of a
    millimeter, is finer than a reader can see on paper.
  - **150 dpi** can miss a move of up to 0.45pt, just inside that bound.
  - **Lower resolutions** save little. 72 dpi would cut the two comparisons'
    combined time by ~18ms and the committed PNG by about half a megabyte, but
    could miss a move of nearly a full point — enough to set text on its rule.
    Around 135 dpi is the lowest that stays within half a point, and it saves
    only ~4ms.
  - **300 dpi** would catch drift no reader could see, for two to three times
    the test time and a committed PNG more than twice the size.
- **Ink-check resolution** {#ink-resolution}: the tests that ask where an
  entry's ink landed render onto the card without its artwork and rasterize at
  300 dpi, `_RASTER_SCALE` in `render_card_test.py`. Their finest margins are
  half a point — the allowance for anti-aliasing above wrapped lines, and the
  gap between a row's edge and the region its underline must not reach — and
  whether an edge's last few tenths of a point show up depends on where they
  fall against the pixel grid. 300 dpi is the smallest round figure that meets
  two requirements:
  - **A pixel at most half the finest margin**: about 290 dpi or finer, so that
    an edge landing a pixel off still leaves half the margin. Coarser grids can
    miss real faults.
  - **Whole-page checks within the budget of ~10ms per test**: the checks that
    rasterize the whole page take ~8ms each at 300 dpi.
- **Unit tests**: the fitting engine, suit markup parsing, and vocabulary
  validation.
- **Rasterizer**: `pypdfium2`, pinned. A new dependency — nothing in the repo
  rasterizes PDFs today, and neither `pypdf` nor `reportlab` can render pixels.
  `pypdfium2` wheels bundle the PDFium renderer, so a pinned version produces
  identical rasters on every machine — unlike `pdf2image`, which shells out to
  whatever poppler the system has — and its license is permissive, unlike AGPL
  `PyMuPDF`.
- **Test speed**: the rendering tests run as part of the default suite. A unit
  test should ideally finish within 10ms, and a handful of rendering tests
  exceed that budget: whole-card rasters, full-card renders, and the rule-table
  measurement. But none takes more than a few tens of milliseconds, and the mean
  test latency across the whole suite is a few milliseconds, well within the
  budget. For now, a separate on-demand suite for the slower tests wouldn't earn
  its upkeep.

## Module shape {#module-shape}

One module per concern; the `renderer/` directory listing is the inventory, and
each module's docstring carries its contract.

`renderer/` is a package under the `convention_cards/` import root. Code meant
for sharing across tools, such as `bridgodex_key.py`, sits at that root, and the
renderer's scripts run as modules from there (`python3 -m renderer.<module>`).
Nothing is installed as a package; the root only has to be on the import path.
The root is `convention_cards/` rather than the repo root because the deployed
Streamlit app imports `make_card` by bare name, and that import would break if
the import root moved up to the repo root.

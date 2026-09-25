# Tasks — system notes renderer

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

Design decisions live in `spec.md`; this file tracks the work.

## Typography

**Goal:** settle how the notes look before the stylesheet hardens.

- Open question {#page-numbers}: does the "(p. N)" after each cross-reference
  stay? Ilya deferred the call (2026-09-07), having seen only the HTML then; the
  PDF now shows what it looks like. The numbers down the table of contents are
  not in question — a printed table of contents with no page numbers has nothing
  to point with — and section headings carry no numbers of their own either way.

- Open question {#wide-overflow}: should a section taller than even a full wide
  page flow onto following pages (today's behavior — three fixture sections do)
  or fail the render, forcing the author to split the section? Surfaced
  2026-09-12 by the render's new page-count guard, which tolerates the flow
  whenever a wide atom exists.

- Open question {#marker-prominence}: the marker ladder stops shrinking after
  the third round — the bullets at depths 5–6 are its smallest shapes, and the
  triangles at 7–12 are larger again. Reordering the pairs would restore the
  taper, at the cost of changing the markers at depths 5–6, which the real notes
  already use (raised 2026-09-20). Ilya leans toward reordering but left it
  queued (2026-09-25).

- Open question {#two-grays}: `.date` is `#555` and the print header and footer
  `#666`, a hair apart. One token would serve both, at the cost of changing one
  of the two renderings (raised 2026-09-20). Ilya left the call to Claude, who
  chose both grays, to settle soon after landing (2026-09-25).

- [ ] **Close the underline gap under suits in screen headings**
      {#heading-underline-gap} — a subsection heading's underline breaks beneath
      each suit symbol on screen, because browsers draw no ancestor's underline
      through the inline-block a suit is set in; print draws it whole. Ilya saw
      it (2026-09-25) and finds it clumsy. Giving the suit its own underline was
      tried and is worse: it draws in the suit's color at the suit face's
      metrics. The fixture has no suit in a subsection heading; rendering one
      such as `## Responses to 1H and 1S` shows the gap.

- [ ] **Explore serif alternatives to IBM Plex Serif** {#serif-alternatives} —
      render the fixture in a few more open-licensed serifs and compare on paper
      at 11pt, against the letterform preferences in `spec.md` #appearance.
  - Note: Plex Serif is the working choice; Inter and Open Sans are the recorded
    sans-serif fallbacks. The prototype's per-font sample renderer
    (`bridge-private/scratch/system_notes_prototype/font_samples/`) is the
    starting point.
  - Note: a new body face means a new italic angle, and the suit skew in
    `notes.css` must follow — enforced by
    `test_suit_skew_tracks_the_body_font_italic_angle`, which fails until the
    stylesheet matches the installed italic.

---

## Backlog

- [ ] **Spike: Typst as the PDF engine** {#typst-spike} — render the fixture
      from the same `notes.md` via pandoc's Typst writer and a template that
      packs sections natively (`measure()` plus scripted placement), and compare
      against the WeasyPrint output.
  - Rationale: the packing WeasyPrint leaves to `print_layout.py` is a
    first-class layout concern in Typst, and this is the second WeasyPrint
    limitation engineered around (after `column-span: all`). Escape hatch if
    quirks keep accumulating; switching costs a second styling system beside the
    CSS, plus Typst branches in the notation filters.
- [ ] **Pack pandoc's footnote endnotes** {#pack-footnotes} — pandoc appends a
      `<section id="footnotes">` after the sections wrapper, where the packer
      can neither measure nor place it, so `paged_document` now refuses
      documents with footnotes. Fold the endnotes into the packed run to lift
      the refusal.
- [ ] **Per-level list markers in the source** {#source-list-markers} — an
      autoformatter giving each indentation depth its own list marker, so the
      Markdown source reads like the rendered page.
  - Note: Markdown has only three unordered markers (`-`, `*`, `+`), which
    pandoc treats identically, so markers would cycle below three levels — and
    prettier normalizes all three to `-` (verified with prettier 3.9), so the
    repo's Markdown formatting hook would undo them; the formatter must exclude
    these files or run after it.

- [ ] **Read the Lua filters for readability as a set** {#lua-readability} —
      Ilya asked (2026-09-21) whether the filters could read better overall, and
      chose to take it up after the branch lands (2026-09-25).

- [ ] **Decide which links carry a page number** {#numbered-references} — every
      link to a heading is page-numbered in print today, which would put "(p.
      7)" on each of the six `[MTB](#mtb)` mentions in the Callahan notes.
      Telling a pointer from a mention needs something the author writes — a
      pandoc link attribute, say — weighed against keeping the notation tiny.
      Whether the empty-link form earns its place belongs here too: Ilya has
      never written one, and it expands to the full heading title where his
      lines abbreviate (2026-09-21). Whether the numbers stay at all is
      #page-numbers. A `term` class keyed on whether the author typed the link
      text was tried and dropped: it styled `[Stayman](#stayman)` and
      `[](#stayman)` differently though both render "Stayman", and it fired on
      all 26 links in the Callahan notes, none of which is empty.

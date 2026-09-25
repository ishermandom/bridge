# Tasks — system notes renderer

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

Design decisions live in `spec.md`; this file tracks the work.

## Typography

**Goal:** settle how the notes look before the stylesheet hardens.

- Open question {#wide-overflow}: should a section taller than even a full wide
  page flow onto following pages (today's behavior — three fixture sections do)
  or fail the render, forcing the author to split the section? Surfaced
  2026-09-12 by the render's new page-count guard, which tolerates the flow
  whenever a wide atom exists.

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

- [ ] **Decide whether and where references carry page numbers** {#page-numbers}
      — every link to a heading is page-numbered in print today, as "(p. N)"
      after its text. The numbers down the table of contents are not in
      question, since a printed table of contents with no page numbers has
      nothing to point with, and section headings carry no numbers of their own
      either way.
  - Open question: whether the "(p. N)" stays at all. Ilya deferred the call
    (2026-09-07), having seen only the HTML then; the PDF now shows what it
    looks like.
  - Open question: if it stays, which links carry one. Today every link does,
    which would put "(p. 7)" on each of the six `[MTB](#mtb)` mentions in the
    Callahan notes. Telling a pointer from a mention needs something the author
    writes — a pandoc link attribute, say — weighed against keeping the notation
    tiny.
  - Open question: whether the empty-link form earns its place. Ilya has never
    written one, and it expands to the full heading title where his lines
    abbreviate (2026-09-21).
  - Note: a `term` class keyed on whether the author typed the link text was
    tried and dropped: it styled `[Stayman](#stayman)` and `[](#stayman)`
    differently though both render "Stayman", and it fired on all 26 links in
    the Callahan notes, none of which is empty.

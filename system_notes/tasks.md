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

- [ ] **Per-level list markers in the source** {#source-list-markers} — an
      autoformatter giving each indentation depth its own list marker, so the
      Markdown source reads like the rendered page.
  - Note: Markdown has only three unordered markers (`-`, `*`, `+`), which
    pandoc treats identically, so markers would cycle below three levels — and
    prettier normalizes all three to `-` (verified with prettier 3.9), so the
    repo's Markdown formatting hook would undo them; the formatter must exclude
    these files or run after it.

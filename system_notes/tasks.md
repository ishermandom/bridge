# Tasks — system notes renderer

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

Design decisions live in `spec.md`; this file tracks the work.

## Typography

**Goal:** settle the open serif choice before the stylesheet hardens.

- [ ] **Explore serif alternatives to IBM Plex Serif** {#serif-alternatives} —
      render the fixture in a few more open-licensed serifs and compare on paper
      at 11pt, against the letterform preferences in `spec.md` #appearance.
  - Note: Plex Serif is the working choice; Inter and Open Sans are the recorded
    sans-serif fallbacks. The prototype's per-font sample renderer
    (`bridge-private/scratch/system_notes_prototype/font_samples/`) is the
    starting point.

# ACBL card renderer — tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Card wording

- [ ] **Explain the name-only entries** {#explain-name-only-entries}: three
      entries assign an agreement a name without communicating its content,
      which makes them near-useless to opponents who don't know the name:
      `other.vs_very_strong` ("Thompson"), `two_level.2c_other` ("Kokish 2!H;
      Parrish 2!S"), and the "XCC M super-accepts" clause of `1_no_trump.more`.
      Reword each to say what the agreement means.
  - Note: space is the constraint — the full Thompson scheme fit its narrow
    blank only at 5.27pt on two lines. If wording alone can't fit, the user's
    candidate mechanism: a curated allowlist of multiline fields rendering at
    ~5.9pt, scooched down a hair to clear the row above.
  - Note: the same principle is why "Wolff signoff" in `other.more2` keeps its
    second word despite a shorter edit being available — don't re-suggest
    trimming it.

---

## Specimen scripts

- [ ] **Let the palette specimen reuse the renderer beside it**
      {#palette-specimen-reuse}: it predates living here, so it still hand-rolls
      its neighbors' concepts — literal `SAMPLE_RUNS` `(text, suit)` tuples
      where `markup.parse_suit_markup` could parse a sample line, and its own
      suit-glyph constants where `Suit` carries the open forms.
  - Note: raised 2026-08-23 during the move, and deferred so the move stayed a
    faithful copy. Not mechanical: the script explores candidate palettes and
    forms, so some hand-rolled pieces are the point — reuse only where a
    renderer symbol is genuinely the same fact (the sample-run shape, the chosen
    glyph forms), not the exploration grid.

---

## Print palette

- [ ] **Add a black-and-white vs. color print option** {#print-color-mode}: the
      cards usually print in black and white, where the four-color suits
      halftone to uneven grays — the orange diamond lightest. The user's
      proposal (2026-08-24): let the render script take the target print mode
      and color entry text and suit symbols to match — the full palette for a
      color print, black or darkened tones for black and white.

---

## Test robustness

- [ ] **Catch an underline extension that stops short** {#extension-short-side}:
      `_has_rule_extension` looks for red anywhere in a 5pt strip ending just
      before the expected edge, so a bar stopping up to ~5pt early still passes
      — the majors test would accept an extension ending at 435 instead of
      438.1. The overrun side is already pinned to half a point, and the
      full-export golden doesn't cover the majors row: its entry is too short to
      extend.
  - Open question: how narrow the strip can get. The strip was presumably kept
    wide so an entry's descenders crossing the bar near its end can't hide all
    the red; measure how far the last glyphs reach before choosing a width.

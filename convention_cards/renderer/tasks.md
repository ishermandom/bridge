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

## Suit symbols

- [ ] **Compare STIX Two Math with Apple Symbols for the suits** {#stix-suits}:
      the card draws its suit symbols in Apple Symbols, the one font the
      renderer still takes from the machine rather than the repo's `fonts/`.
      STIX Two Math, already in `fonts/`, draws the system notes' suits; print a
      card in each and compare legibility, size, and the open (outlined) forms
      the card uses.
  - Note: a switch moves more than the glyphs — the suit-size calibration in
    `fonts.py`, the palette specimen's ~0.56 em assumption, and the filled-card
    goldens all follow the face.

---

## HTML card

- [ ] **Load the HTML card's fonts from Google Fonts on screen**
      {#html-card-web-fonts}: the hand-built HTML card in `bridge-private` names
      Roboto Condensed, Source Sans 3, and IBM Plex Sans but loads none of them,
      so a browser shows whichever the machine has installed. Link the three
      families from Google Fonts in the card's HTML; Google's versions may drift
      from the repo's, which is fine for screen viewing.
  - Note: `make_two_sided_card.py` renders the same HTML in Chromium, so it must
    block requests to Google's font servers, leaving the printout on the repo
    files it already injects.

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

## Test speed

- [~] **Keep the default suite to fast unit tests** {#test-latency}: the user's
  bar is that a unit test runs within ~10ms, and anything slower belongs in a
  separate suite. Either make the rendering tests fast enough to meet it, or
  move them to a suite that runs on demand rather than on every turn.
  - Note: measured 2026-09-14, after the placement checks left the card's
    artwork behind — the suite takes ~0.60s in pytest, down from 5.2s before the
    speedups. About a quarter-second of that is startup (imports, fonts, the
    base card's parse), which no change to a test touches. Eight tests remain
    over the bar, 0.27s together:
    - **The blank-card identity check**, ~63ms: two full-page rasters at 300
      dpi, plus PDFium's first-use warm-up. It carries the core pixel-perfection
      guarantee.
    - **Full-export renders**, ~16ms each: the golden (~43ms with its 150-dpi
      raster) and the full-export text check (~22ms) each render the same card.
    - **Field-geometry loads**, ~26ms each, three per run: the base card's load,
      `geometry_test`'s first test, and the rule check (~62ms). ~20ms of the
      rule check's time is a garbage collection that usually lands there,
      clearing what earlier renders left behind; alone, it takes ~44ms.
    - **Renders**, 6ms each: the base card's stay-blank check makes three
      (~22ms), and the default-size check adds a 5ms text read to one (~13ms).
    - **The two-sided composition check**, ~17ms, with occasional outliers.

    Rerun pytest over `convention_cards` with `--durations=20` for the current
    list.

  - Note: cheap candidates — render the full export once for both tests that
    need it (~16ms), which also retires the text check's own copy of
    `renderable_full_export`'s key removal; and load the field geometry once per
    run, sharing it (~50ms).
  - Open question: whether to split the slow tests out, and how. A spike that
    deselected fifteen of them measured the per-turn run at 0.34s. Claude's
    recommended shape: mark them `slow`; a root `conftest.py` deselects `slow`
    only when `PYTEST_FROM_HOOK` is set — the Stop hook sets it and nothing
    reads it yet — so every other run stays complete; and `git land` runs the
    full suite between its rebase and fast-forward, a dotfiles change. CI can't
    take the slow suite: the base card and fonts are private assets. Running
    tests in parallel (root `tasks.md` #parallel-pytest) would absorb most of
    these into its floor, which may make the split unnecessary.

---

## Test robustness

**Goal:** the pixel tests in `render_card_test.py` keep testing what they claim
when the card's layout changes, rather than going stale or passing vacuously.

- [ ] **Cover the majors row's underline extension** {#majors-extension-test}:
      every extension test exercises the 1NT family, and the golden's majors
      "Other" entry fits, so nothing renders the majors row's extension, which
      ends at x=438.1 in the darker ED1C24 red. One test rendering without the
      card's artwork, a few milliseconds, would cover it.
- [ ] **Check underline extensions by what's drawn, not by red pixels**
      {#drawn-extension-checks}: read the page's drawing instructions, as
      `measure_rule_positions.py` does, and assert a bar in the panel's red from
      the printed end to the shared edge at the rule's height. Do it with
      #print-color-mode, whose black-and-white option would break the red-ink
      detection anyway.
  - Note: keep pixel checks where pixels are the point — the blank-card identity
    test and the golden.

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

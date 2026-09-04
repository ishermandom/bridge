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

## Landing

- [~] **Review the branch commit by commit** {#branch-review}: production code
  never lands unreviewed (#review-gate). The branch history is rebuilt as a
  sequence of independent commits, each meant to stand on its own —
  `git log --reverse main..worktree-card-renderer` is the queue.
  - Reviewed: every commit but the last, the SWAN–Bridgodex converter
    (2026-09-13). The user moved that commit to the back of the queue so the
    rest can land first (#land-branch); #swan-review covers it.
  - Note: the proofread pass over the series also flagged main's
    `session_analysis/private_paths.py` "That checkout" ambiguity — a one-line
    fix belonging to that subtree's thread.

- [ ] **Land the reviewed commits** {#land-branch}: everything on
      `worktree-card-renderer` before the SWAN–Bridgodex converter, which stays
      on the branch for #swan-review. Needs the user's go-ahead. The main
      checkout holds a stray untracked `convention_cards/data/acbl.pdf`; the
      branch no longer has a `data/` directory, so delete the stray as cleanup
      when landing. The branch expects `bridge-private` beside the checkout
      (base PDF, fonts — discovered by `renderer/private_paths.py`).
  - Note: more cleanup at landing — drop the three tagged stash snapshots
    (`card-renderer-*-20260824`) and the `backup/card-renderer-file-history`
    branch; each was verified byte-redundant with committed history when taken.
  - The two-sided print flow must land before bridge-private's
    `callahan/regenerate.sh` works — the wrapper points at the main checkout,
    where `renderer/make_two_sided_card.py` doesn't exist until landing.
  - At landing, bridge-private's `callahan/regenerate.sh` must switch from
    launching `make_two_sided_card.py` by path to module form —
    `python -m renderer.make_two_sided_card`, run from the checkout's
    `convention_cards/` (spec.md #module-shape). Committing it needs the user's
    go-ahead.
  - The bridge-private side is otherwise fully committed (2026-09-12): the
    proofed card state, the self-contained wrapper, and the Bridgodex captures.
    The Callahan `print-ready.pdf` was then regenerated with per-field rule
    placement (bridge-private `08e8007`), newer than the 2026-08-24 physical
    proof.
  - Note: layout per `renderer/make_two_sided_card.py`'s docstring; the HTML
    card fits with ~17pt of height to spare — no warning.
  - Note: the physical proof passed (2026-08-24) — duplex registration, the
    book-page flip in hand, and the holder fit with the one cut.

- [ ] **Split and review the SWAN–Bridgodex converter** {#swan-review}: once
      #land-branch lands the rest, break "Convert cards between SWAN and
      Bridgodex, both directions" into several smaller commits, and review
      those. The user asked for the split (2026-09-13).
  - Note: raise during that review — `swan/bw_lead_bolds.py` imports pypdfium2
    at run time, but `convention_cards/pyproject.toml` declares it only in the
    `dev` group.

---

## Test speed

- [ ] **Keep the default suite to fast unit tests** {#test-latency}: the user's
      bar is that a unit test runs within ~10ms, and anything slower belongs in
      a separate suite. Either make the rendering tests fast enough to meet it,
      or move them to a suite that runs on demand rather than on every turn.
  - Note: measured 2026-09-13 — the subproject's 81 tests took 4.3s, 3.55s of it
    in `render_card_test.py`, whose 17 full-card renders cost 0.13–0.35s each.
    Also over the bar: `rule_positions_test.py`'s fresh measurement (0.36s, a
    1200-dpi render), three `geometry_test.py` tests (~30ms each), and two
    `make_two_sided_card_test.py` tests (10–20ms). Rerun pytest over
    `convention_cards` with `--durations=30` for the current list.
  - Open question: if the slow tests move to an on-demand suite, what runs that
    suite before landing, so a rendering regression can't reach `main` unseen.

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

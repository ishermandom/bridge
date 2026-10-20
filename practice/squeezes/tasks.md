# Squeeze trainer tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Stage 1: automatic simple squeeze endings

**Goal:** play generated automatic-simple-squeeze endings in the browser against
quantum defenders, with BridgeMaster-style error stops.

- [ ] Ilya's React learning exercises: `rg 'TODO\(ilya\)' scratch/ui/src`
- [ ] Post-mortem view: after success, show a second layout the same line
      handled; after failure, replay to the erring card
- [ ] Problem variation review: confirm generated spot-card/suit variety feels
      fresh across a practice session

---

## Backlog

- [ ] **Speed up `generation_test.py` and return it to the repo's test run**
      {#restore-generation-tests}: `run_tests.sh` leaves it out, because it took
      2–3s of every turn's Stop hook while this project is paused.
  - Note: each test certifies a generated problem by exhaustive search in
    `solver.py` — about 537,000 positions across the file, each a
    frozen-dataclass copy plus hashing. The `[6-3]` case alone takes 1–2s.
- [ ] Positional simple squeezes (fast follow per spec.md #curriculum)
- [ ] Rectify-the-count problems (duck a trick before the squeeze operates)
- [ ] Full 13-card deals: pad endings with idle early tricks; adopt `endplay`
      for double-dummy checks at that size
  - Note: `endplay` has no Python 3.14 wheels but builds from sdist — verified
    2026-08-04.
- [ ] Mixed sets: ~half squeezes, ~half look-alikes (finesse as percentage
      play); weighted families per spec.md #generation
- [ ] Seed and cross-check problems against open corpora: Wikipedia's squeeze
      articles (CC BY-SA, ~87 position diagrams), Love's _Squeeze Play in
      Bridge_ (1951, US copyright unrenewed → public domain), and _Lenz on
      Bridge_ (1926, public domain). Love 1959 and the bridge sites are
      all-rights-reserved — inspiration only.
- [ ] Progress tracking (streaks, per-stage mastery) — nice-to-have
- [ ] Trump contracts (engine is notrump-only today)
- [ ] UI tests (vitest + jsdom) once the UI stabilizes out of scratch
- [ ] Graduation: review scratch code up to production bar, move out of
      `scratch/`, reconcile card vocabulary with `session_analysis` models

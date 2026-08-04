# Squeeze trainer tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Stage 1: automatic simple squeeze endings

**Goal:** play generated automatic-simple-squeeze endings in the browser against
quantum defenders, with BridgeMaster-style error stops.

- [~] Exact quantum solver, engine, generator, FastAPI server, React UI
- [ ] Post-mortem view: after success, show a second layout the same line
      handled; after failure, replay to the erring card
- [ ] Problem variation review: confirm generated spot-card/suit variety feels
      fresh across a practice session

---

## Backlog

- [ ] Positional simple squeezes (fast follow per spec.md #curriculum)
- [ ] Rectify-the-count problems (duck a trick before the squeeze operates)
- [ ] Full 13-card deals: pad endings with idle early tricks; adopt `endplay`
      for double-dummy checks at that size
  - Note: `endplay` has no Python 3.14 wheels but builds from sdist — verified
    2026-08-04.
- [ ] Mixed sets: ~half squeezes, ~half look-alikes (finesse as percentage
      play); weighted families per spec.md #generation
- [ ] Progress tracking (streaks, per-stage mastery) — nice-to-have
- [ ] Trump contracts (engine is notrump-only today)
- [ ] UI tests (vitest + jsdom) once the UI stabilizes out of scratch
- [ ] Graduation: review scratch code up to production bar, move out of
      `scratch/`, reconcile card vocabulary with `session_analysis` models

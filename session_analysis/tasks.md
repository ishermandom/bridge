# Session analysis — digitization tasks

Implementation tracker for the scoresheet digitization pipeline. Design and
rationale live in [spec.md](spec.md) and [models.md](models.md); this file
tracks work, not decisions.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

The phases follow the spec's build order: the pure-logic core first (zero OCR,
fully testable, de-risks everything downstream), then extraction,
reconciliation, ingest, and the review UI.

---

## Scaffolding

**Goal:** a Python package under `session_analysis/` with test infrastructure,
matching the repo's conventions.

- [x] Set up the package layout and test infrastructure (package, pytest).
  - Note: `pyproject.toml` and the Pydantic dependency are deferred to the
    models task — the first piece that needs a third-party dependency.
- [x] Wire the package's tests into the repo's `run_tests.sh`.

---

## Pure-logic core

**Goal:** the testable heart — notation, models, parsing, and validation — built
and verified with no OCR involved.

- [x] Notation normalizer: `±N` → `tricks_taken`, with exhaustive unit tests.
      #normalizer
  - Note: `notation.py` covers the sheet convention; the traveller convention
    lands with reconciliation, when it's first needed.
- [ ] Pydantic models and enums: Session, Board, Call, Contract, Result, Card,
      Announcement, Issue. Lenient content leaves; typed skeleton.
- [ ] Dealer/vul computation from board number, table-driven test across a full
      16-board cycle.
- [ ] Auction + contract string parser: VLM strings → canonical model. Depends
      on #normalizer.
  - Note: the auction grammar handles boxes spanning calls and wrapping circled
    ones; unparseable tokens become issues, never failures. See models.md
    (Parsing).
- [ ] Non-raising validation pass: returns issues with severity; never aborts.
  - Content well-formedness: each call, lead, and contract resolved to canonical
    values; contract level in 1-7; `tricks_taken` in 0-13; result notation
    consistent with the contract (a `+N` make must not imply fewer tricks than
    the contract needed). These range and consistency checks are deferred here
    from the notation translator, which only parses.
  - Auction legality: rank monotonicity, contract = last call, declarer
    derivable and consistent.
  - Card legality: the opening lead is a real card.

---

## Extraction

**Goal:** a sheet image becomes the VLM's compact per-board string output,
parsed into the canonical model.

- [ ] Headless Claude invocation: `claude -p` with `--system-prompt`, `--bare`,
      the `Read` tool on the scan path, `--output-format json`,
      `claude-sonnet-5`.
- [ ] VLM extraction prompt: transcribe-don't-interpret; the auction/contract
      syntax; drop scratch-outs; no score; no dealer/vul. #vlm-prompt
  - Open question: the prompt is unwritten — see models.md (Open questions).
- [ ] Wire extraction output through the parser to the canonical model and the
      validation pass.

---

## Reconciliation

**Goal:** cross-check the digitized session against the travellers and surface
likely row swaps.

- [ ] Traveller HTML parsers (ACBL Live, club site) → recoverable fields.
- [ ] Join on session + pair + `Vs`; cross-check recoverable fields; raise
      review priority on disagreement.
- [ ] Best-alignment permutation swap detection — suggest, never auto-apply.
      Test against the 6/29 board-20/21 swap.
- [ ] Graceful degradation: run to completion with zero travellers.

---

## Ingest

**Goal:** get a scan from the phone onto the Mac and into the inbox pipeline.

- [ ] Choose the scanner app and transport.
  - Open question: Android scanner + Drive-mirror vs. Syncthing — see spec.md
    (Open questions) and the Ingest section's tradeoffs.
- [ ] Inbox spine: `inbox/` → `processed/<session-key>.json` + image →
      `archive/`, idempotent on header + content hash.
- [ ] Header self-naming → session key, confirmed in review before commit.
- [ ] The "process inbox" command.

---

## Review UI

**Goal:** a minimal, standalone tool to correct flagged fields, image beside
parsed value.

- [ ] Choose the tech (FastAPI + htmx, or Gradio).
  - Open question: framework, keybindings, commit semantics — see spec.md (Open
    questions).
- [ ] Triage-ranked field list with image crop beside the parsed value and
      keyboard accept/fix.
- [ ] Row-level fixups (swap, renumber, reorder) as first-class operations.
- [ ] Re-validate after edits; auto-open or notify after a sheet is processed.

---

## Backlog

Forward-looking items parked until their phase or trigger arrives; all are
settled as open questions in [spec.md](spec.md#open-questions).

- [ ] Final storage format (queryable DB) and the JSON → DB migration.
- [ ] Local traveller archive and index, so access doesn't depend on third-party
      servers.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller.
- [ ] Model escalation: a stronger-model fallback for low-confidence auction
      rows, if single-model accuracy proves insufficient.

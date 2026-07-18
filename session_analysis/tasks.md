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
- [x] Pydantic models and enums: Session, Board, Call, Contract, Result, Card,
      Announcement, Issue — a typed skeleton with per-token parse envelopes. See
      models.md and models.py. The parser and validation tasks below parse into
      and over this model.
- [x] Dealer/vul computation from board number, table-driven test across a full
      16-board cycle.
- [x] Auction + contract string parser: VLM strings → canonical model. See
      `parsing.py` and models.md (Parsing, Announcement decoding).
- [x] Reviewed `parsing.py`/`parsing_test.py` with Ilya; applied the follow-ups
      in code and models.md: `NT` spelling everywhere, order-free NT ranges, the
      `minimum_points_is_soft` field, 'pass'-substring passout, `x`/`xx`
      doubles, trailing-only alerts, decomposed regexes, and two refocused
      auction tests (realistic composition + legality-agnostic).
- [x] Lead parser: `10S` → `Card` in a `Lead` envelope. #lead-parser
- [x] Board-number parser: `7` → `Schedule` via `board_rotation`, in a
      `BoardNumber` envelope. #board-number-parser
- [x] Header parser: date from the header transcription. #header-parser
  - Note: the date is month/day with no year (`6/29`); `parse_header` infers the
    year against a scan-date argument, reading the month/day as its most recent
    past occurrence (a December sheet scanned in January is the prior year).
    Assembly supplies the scan date.
  - Note: our own pair is deliberately not read from the sheet — a pair
    identifier is number + direction (sometimes a section), not a bare int, and
    it comes more directly from the travellers. Resolved at reconciliation; see
    the reconciliation phase.
- [x] Non-raising validation pass: `find_issues(board)` plus `validate_board`/
      `validate_session` that annotate frozen copies. See `validation.py` and
      models.md (Validation).
  - Note: `validation.py`/`validation_test.py` are written and green but
    uncommitted, awaiting an `/ownership-walkthrough` deferred to a later
    session — the diff hasn't had its ownership review yet.
  - Note: the `+N`-make-reaches-the-contract check is deliberately left for the
    parser rather than done here. The `+`/`-` sign is still recoverable from
    `Outcome.raw`, but is already gone from the typed `Result.tricks_taken` this
    pass reads, so checking it here would mean re-parsing raw cell text.
    `parse_contract_cell` already has the sign in hand mid-parse, so the check
    belongs there instead.
  - Note: card legality collapses into lead resolvability — a `Card` is built
    from enum-typed rank and suit, so any resolved lead is already a real card.
  - Note: the declarer is not derived from the auction — passes are usually
    unwritten, so seats can't be reconstructed and even the opening side is
    ambiguous. The contract cell's declarer stands; cross-checking it moves to
    reconciliation against the travellers. Auction legality instead leans on
    `by_opponents` (the circle convention) for its double/redouble side checks.
- [ ] Make-vs-set result consistency, in the parser: when a contract cell's
      result reads `+N`, verify the make reaches the contract — `tricks_taken`
      at least `level + 6` — and attach an `Outcome` issue when it doesn't.
      #make-reaches-contract
  - Rationale: the sign survives in `Outcome.raw`, so the validator could
    re-parse it, but only by duplicating parsing logic on text the parser
    already parsed. `parse_contract_cell` holds both the sign and the level
    mid-parse without any re-parsing, so the check belongs there.

---

## Extraction

**Goal:** a sheet image becomes the VLM's compact per-board string output,
parsed into the canonical model.

- [ ] Headless Claude invocation: `claude -p` with `--system-prompt`, `--bare`,
      the `Read` tool on the scan path, `--output-format json`,
      `claude-sonnet-5`.
- [ ] VLM extraction prompt: transcribe-don't-interpret; the auction/contract
      syntax; drop scratch-outs; no score; no dealer/vul; no pair numbers.
      #vlm-prompt
  - Open question: the prompt is unwritten — see models.md (Open questions).
  - Note: a circled board number is emitted with parentheses — `(7)`, reusing
    the auction's circle convention; assembly strips them and sets
    `Board.flagged_for_review`.
  - Note: the header date must be emitted as numeric month/day (`6/29`),
    normalizing whatever the human wrote ('June 9th', `6.23`, `June 9`). The
    parser assumes this normalized form and infers only the missing year; it
    does not read free-form date prose. Normalizing is left to the VLM, which
    reasons through the variants far more easily than a regex would.
- [ ] Wire extraction output through the parser to the canonical model and the
      validation pass.
  - Note: parse the VLM JSON into `assembly.RawSession`, then
    `assembly.assemble_session` into the canonical `Session`. Per-cell and
    per-board errors are already contained; `RawSession.model_validate_json`
    still raises when the top-level shape is fundamentally wrong (not an object,
    or `boards` not a list), so wrap that call and flag the whole sheet on
    failure rather than letting it abort extraction.

---

## Reconciliation

**Goal:** cross-check the digitized session against the travellers and surface
likely row swaps.

- [ ] Traveller HTML parsers (ACBL Live, club site) → recoverable fields.
  - Note: this phase defines the richer traveller type that replaces
    `Source.travellers`, currently a placeholder `tuple[str]` of path/URL refs.
- [ ] Join on session + board content; cross-check recoverable fields; raise
      review priority on disagreement.
  - Note: neither pair identity is on the digitized session — both ours and the
    opponents' are resolved here from the matched traveller (number + direction,
    sometimes section), not read from the sheet. Settle their type alongside the
    traveller type above.
  - Note: the declarer is one such recoverable field — the validator can't check
    it (an auction with implicit passes gives no seats), so it's cross-checked
    here. Neither the sheet nor the traveller is the source of truth: travellers
    are sometimes wrong where the local notes are right, so surface a
    disagreement for review rather than trusting either side.
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

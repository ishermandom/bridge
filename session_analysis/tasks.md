# Session analysis — digitization tasks

Implementation tracker for the scoresheet digitization pipeline. Design and
rationale live in [spec.md](spec.md) and [models.md](models.md); this file
tracks work, not decisions.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

The phases follow the spec's build order: the pure-logic core first (zero OCR,
fully testable, de-risks everything downstream), then extraction,
reconciliation, ingest, and the review UI.

---

## Extraction

**Goal:** a sheet image becomes the vision model's compact per-board string
output, parsed into the canonical model.

- [x] Build the pipeline: headless invocation (`vision_model_invocation.py`),
      extraction prompt (`extraction_prompt.md`), per-cell parsers, and the
      `parse_and_assemble_session` entry point — exercised end to end against a
      real scan (the 6/29 sheet). #live-extraction-test
  - Note: live transcription error profile (24 played boards): footer, leads,
    and board numbers all correct; one contract-result misread (`+4` for `+3`);
    every auction error was markup, not calls — dropped circles (3 boards), a
    dropped box, dropped `_H`/`_E` announcements (one surfaced as a rank
    violation), a circled `*` glued into `1H*`. Feeds prompt tuning and the
    model-escalation backlog item.
- [ ] Give the extraction JSON schema a production home: the session/board
      schema passed as `--json-schema` exists only in the live-test scratch
      driver; the "process inbox" command will need it in the package.
- [ ] Decide handling for unplayed pre-printed rows: boards 25–28 come back as
      all-empty objects and each draws a medium `contract_missing` issue —
      either the prompt omits rows with no writing, or downstream treats an
      all-blank board as unplayed rather than flagging it.

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
      `archive/`, idempotent on footer + content hash.
- [ ] Footer self-naming → session key, confirmed in review before commit.
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
  - Note: an unresolved auction token is currently flagged twice with no shared
    identity — once as `unparseable_call` on the `AuctionEntry` itself
    (parsing.py) and again as `unresolved_call` at the board level
    (validation.py). Worth a shared issue-identity scheme (see models.md's open
    question on firming up issue codes) so it isn't listed twice.
  - Note: a session has few enough boards that raw issue counts barely move
    triage order either way; `Issue.severity` is the real priority signal, so
    triage should rank by severity, not by a count.
- [ ] Row-level fixups (swap, renumber, reorder) as first-class operations.
- [ ] Re-validate after edits; auto-open or notify after a sheet is processed.
  - Note: `validate_board` appends freshly found issues onto `board.issues`
    unconditionally, with no de-duplication. Re-validating the same board twice
    (an edit that didn't touch the flagged field, or a retry) will accumulate
    duplicate `Issue` entries unless this task also strips prior
    validation-origin issues before re-running the checks.

---

## Backlog

Forward-looking items parked until their phase or trigger arrives; all are
settled as open questions in [spec.md](spec.md#open-questions).

- [ ] Final storage format (queryable DB) and the JSON → DB migration.
- [ ] Local traveller archive and index, so access doesn't depend on third-party
      servers: store in the bridge-private repo.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller.
- [ ] Model escalation: a stronger-model fallback for low-confidence auction
      rows, if single-model accuracy proves insufficient.

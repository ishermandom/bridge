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

- [x] Headless Claude invocation: `claude -p` with `--system-prompt`,
      `claude-sonnet-5`. See `vision_model_invocation.py`.
- [x] Vision model extraction prompt: transcribe-don't-interpret; the
      auction/contract syntax; drop scratch-outs; no score; no dealer/vul; no
      pair numbers. See `extraction_prompt.md`. #vision-model-prompt
  - Note: not yet exercised against a live model.
- [ ] Parser support for boxed and struck-through cells outside the auction.
      #boxed-and-struck-through
  - Note: the prompt now has the vision model transcribe a struck-through cell —
    contract, lead, or auction — as the fixed token `---`, and wrap a boxed lead
    or contract in square brackets (`[10oS]`, `[6H*W-1]`), the same convention
    already used for boxed auction calls. See `extraction_prompt.md`. The model
    transcribes; this task is where the parser catches up to what it can now
    produce.
  - Note: `parse_contract_cell` already treats a run of dash glyphs as a passout
    (`_STRUCK_THROUGH_PATTERN`, `parsing.py`), and `---` fullmatches it, so the
    contract side needs no change. `parse_lead` and `parse_auction` have no
    equivalent — a struck-through lead or auction cell currently fails to parse
    and raises a spurious issue instead of resolving cleanly, the way an empty
    cell already does in `assembly.py`.
  - Note: `Lead` has no `flagged_for_discussion`-style field for a boxed lead
    (only `AuctionEntry` does). Decide whether `Lead`/`Outcome` need one, or
    whether a boxed lead/contract should fall back to the same review-flagging a
    parse failure already gives.

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
    (validation.py). A priority score built from raw issue counts would
    double-count it; worth a shared issue-identity scheme (see models.md's open
    question on firming up issue codes) before triage math depends on counts.
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
      servers.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller.
- [ ] Model escalation: a stronger-model fallback for low-confidence auction
      rows, if single-model accuracy proves insufficient.

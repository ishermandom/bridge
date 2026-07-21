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
- [ ] Tokenize glued calls in the auction parser: the vision model sometimes
      omits the space between adjacent tokens, and the parser should split them
      locally rather than expect the model to police spacing. Observed live:
  - Adjacent circled calls: `(1D)(1S)`, `(1D)(1N)`, `(1D)(1H)`, `(3S)(4S)`,
    `(1N)(3N)`, `(1D)(1S)(1N)`, `(1C!)(1S!)(1N)`, `(1D)(1H)(1N)(2H)`.
  - A double glued to its call: `1H*` (a circled `*` on the sheet, emitted fused
    with the preceding call).
- [ ] Decide handling for unplayed pre-printed rows: boards 25–28 come back as
      all-empty objects and each draws a medium `contract_missing` issue —
      either the prompt omits rows with no writing, or downstream treats an
      all-blank board as unplayed rather than flagging it.
- [ ] Productionize strip-based extraction: send the sheet as per-row crops at
      native resolution instead of one full-sheet image. Validated live on the
      6/29 sheet — the API downscales the full 12MP scan to ~56% linear
      (~3.75MP), and every resolution-class error (the persistent `+4`-for-`+3`
      contract, dropped `_H`/`_E` announcements, box-vs-circle swaps on dense
      rows) vanished with native-resolution strips, at lower cost than the
      full-sheet run ($0.21 vs $0.29).
  - Note: what made the experiment work — include the printed `Bd` column in the
    crop (a crop without it made the model substitute the `Vs` number), precede
    each strip with a text label naming its row, and say explicitly to emit
    blank rows.
  - Note: the experiment hand-tuned this one scan's row geometry; production
    needs the grid found per scan (the printed horizontal rules are strong — a
    projection profile or similar should do) plus the footer region.
  - Note: residual errors after the fix are markup-interpretation, not
    resolution: strikethrough-vs-box confusion and one dense overwritten row.
    Those are the target of the voting task below.
- [ ] Make Opus (`claude-opus-4-8`) the default extraction model
      (`vision_model_invocation._DEFAULT_MODEL`, currently `claude-sonnet-5`).
      On the live strips comparison Opus read markup semantics better —
      strikethrough correctly omitted, circles and cursive notes right — at
      ~$0.25–0.30/run vs Sonnet's ~$0.21.
- [ ] Run extraction twice and vote: two Opus runs over the same strips,
      auto-accept cells that agree, flag disagreements for review.
      #extraction-voting
  - Note: validated live on the 6/29 sheet — the two runs' disagreement sites
    were exactly the error sites (a contract digit, a dropped box and alert, a
    stray call, a note misread), while the agreed-but-wrong residue was two
    dropped `!` marks on one dense row plus a cell the parser already flags.
    ~$0.55/sheet at subscription-notional rates.
  - Note: compare parsed values, not raw strings — runs legitimately vary
    between equivalent notations (`(*)` vs `(x)` for a circled double), which
    the parser normalizes; raw-string voting would flag them falsely.
  - Note: supersedes the Backlog's model-escalation item if it works — that item
    stays parked until this settles.
- [ ] Experiment: have the vision model interpret a missing date instead of
      leaving it to the parser. Validate quality before adopting — this is a
      trial, not a settled direction.
  - Rationale: the date is often not written on the sheet at all, and a vision
    model can plausibly infer it from available context in a way static code
    can't do accurately.

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

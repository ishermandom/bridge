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
- [ ] Make Opus (`claude-opus-4-8`) the default extraction model
      (`vision_model_invocation.DEFAULT_MODEL`, currently `claude-sonnet-5`). On
      the live strips comparison Opus read markup semantics better —
      strikethrough correctly omitted, circles and cursive notes right — at
      ~$0.25–0.30/run vs Sonnet's ~$0.21.
- [ ] Run extraction twice and vote: two Opus runs over the same strips,
      auto-accept cells that agree, flag disagreements for review.
      #extraction-voting
  - Note: strip extraction's residual errors are markup-interpretation, not
    resolution (strikethrough-vs-box confusion, one dense overwritten row) —
    exactly this task's target.
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
- [ ] Explore replacing local geometry processing (dewarp, grid detection, strip
      cutting) with one or more vision-model calls.
  - Rationale: the local pipeline exists largely to work around a resolution
    limitation in Claude's vision input. The code is fragile; solving the
    problem natively in the vision model would be much more robust.
  - Note: if this pans out, it reshapes the Backlog's multi-format geometry item
    — a model-driven approach may handle two-column layouts without a hand-built
    column-grid stage.

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
    question on firming up issue codes) so it isn't listed twice. An unresolved
    opening lead has the same duplication — `unparseable_lead` on the `Lead`
    envelope, `unresolved_lead` again at the board level — and wants the same
    fix.
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
- [ ] Multi-format sheet geometry: support two-column scoresheet layouts (the
      Baron Barclay and Bridge Buddy samples in `bridge-private/scoresheets`).
      Not a detection tweak — needs column-grid segmentation before row
      detection, `SheetGeometry` reshaped as multiple grids with per-grid row
      counts (Baron Barclay prints 16 rows left, 20 right), strip labels that
      carry column identity, and exclusion of the printed VP/IMP scale tables,
      which are themselves uniform grids that pollute the row-count vote.
  - Note: current behavior on the samples — both Baron Barclay forms error
    loudly (ambiguous row count; too few slices), but both Bridge Buddy forms
    return confidently wrong geometry: row boxes spanning both columns (a strip
    would mix two boards) with scale-table rows chained into the grid. Until
    this lands, that silent-wrong mode is the hazard if a two-column scan ever
    enters the pipeline.
  - Note: geometry is the smaller half. These forms have no auction or notes
    columns, so the extraction prompt, output schema, and parser contract are
    club-form-specific too — supporting a new format is a form-template
    decision, not only cropping.
- [ ] Maybe: grid-extent cross-check in `transcribe_sheet` — compare the
      detected `grid_left`/`grid_right` against where the dewarp placed the
      borders by construction (`_DEWARP_SIDE_MARGIN_IN_PITCHES` from the frame
      edges); deviation beyond ~1 pitch raises rather than cutting strips.
  - Rationale: catches asymmetric border failures — a border only partly visible
    resolves in the dewarp's median-filtered bands but dilutes out of
    detection's single full-height column profile, which today silently crops
    the `Bd` column and makes the model substitute `Vs` numbers (observed live).
    Also catches future drift between the two derivations.
  - Note: does not catch uniformly faint borders — both stages then agree on the
    same wrong interior line and the `Bd` column is lost at dewarp time. The
    check lives in `transcribe_sheet`, not `detect_sheet_geometry`, which also
    runs on images that never went through the dewarp.
- [ ] Maybe: board-number continuity check in validation — flag a session whose
      transcribed board numbers don't run consecutively from their start.
  - Rationale: output-side catch-all for geometry failures no pixel check can
    see — a silently truncated grid (washed-out top rows), a shifted grid (a
    header row voted in as row 1), or `Bd`-column loss (substituted `Vs` numbers
    don't run consecutively).
  - Open question: team games may play non-consecutive board sets, so the check
    may need to be format-aware or advisory-only — part of why this is deferred
    rather than queued.

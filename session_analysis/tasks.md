# Session analysis — digitization tasks

Implementation tracker for the scoresheet digitization pipeline. Design and
rationale live in [spec.md](spec.md), [models.md](models.md), and
[travellers.md](travellers.md); this file tracks work, not decisions.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

The phases follow the spec's build order: the pure-logic core first (zero OCR,
fully testable, de-risks everything downstream), then extraction, the traveller
subsystem (parsing, reconciliation, acquisition), ingest, and the review UI.

---

## Extraction follow-ups (deferred)

**Goal:** a sheet image becomes the vision model's compact per-board string
output, parsed into the canonical model.

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

**Goal:** capture the travellers as a game-record database and join them to the
digitized sheet — enriching it with the deal, matchpoints, and pair identities,
and surfacing disagreements and row swaps. Design in
[travellers.md](travellers.md).

- [ ] Traveller data model — `Traveller`/`TravellerBoard`/`TravellerResult`,
      plus the shared `Deal`/`Hand`/`PairIdentity` canonical types (see
      models.md). Replaces the `Source.travellers` placeholder (`tuple[str]`).
- [ ] ACBL Live HTML parser → full traveller (every row, deal, par).
- [ ] Club site HTML parser → full traveller (every row, deal).
- [ ] Find our row by the configured name — either direction, any partner; flag
      when the name is absent.
- [ ] Cross-check recoverable fields; raise review priority on disagreement.
  - Note: the declarer is cross-checked here — the validator can't (an auction
    with implicit passes gives no seats), and neither sheet nor traveller is
    authoritative, so surface the disagreement rather than trusting either side.
- [ ] Merge the two sources; flag disagreements, store both raw records, no
      silent tiebreak.
- [ ] Deal capture + the deal-versus-lead check (opening lead ∈ declarer's LHO
      hand) and deal well-formedness (52 distinct cards, 13 per hand).
- [ ] Best-alignment permutation swap detection — suggest, never auto-apply.
      Test against the 6/29 board-20/21 swap.
- [ ] Graceful degradation: run to completion with zero travellers (no deal, no
      enrichment).

---

## Traveller acquisition

**Goal:** get travellers into the pipeline — auto-fetch where possible, manual
save otherwise — and auto-reconcile when one lands. Design in
[travellers.md](travellers.md#acquisition).

- [ ] Move `session_analysis/travellers/` out of the public repo into
      `bridge-private`; read it through a configurable path.
- [ ] Match a capture to its session by parsed metadata (event + date), not the
      filename or URL.
- [ ] Manual-save fallback: a capture dropped in is picked up and matched.
- [ ] Explore club auto-fetch: scrape the index at
      `paloaltobridge.org/game-results/` and follow the session's link
      (directories vary per director — discover, don't derive).
- [ ] Explore ACBL auto-fetch (club + tournament, player #2475316) past
      Cloudflare — the fetch mechanism is an open investigation.
  - Note: `claude-in-chrome` runs as a separate OS user from the browser, so it
    may not be viable; a headless browser with exported cookies is an
    alternative.
  - Note: tournaments are ACBL-only and higher-value (larger scale), so this is
    the most valuable fetch to automate.
- [ ] Auto-reconcile: a fetched traveller matching a pending session triggers
      reconciliation; review stays deferred until then.
- [ ] Escape hatch: an explicit "finalize without traveller" action for a
      session no traveller arrives for.
- [ ] Store parsed travellers as structured JSON; keep raw HTML lean (drop the
      ACBL `_files` asset bundle).

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
settled as open questions in [spec.md](spec.md#open-questions) and
[travellers.md](travellers.md#open-questions).

- [ ] Final storage format (queryable DB) and the JSON → DB migration.
- [ ] Remote-backed, size-tolerant durable store beyond `bridge-private`, if the
      growing game database outgrows the repo.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller — they carry the deal, too.
- [ ] Pianola as a traveller source, for club games that post only there
      (deferred: the sessions currently played don't use it).
- [-] Model escalation: a stronger-model fallback for low-confidence auction
  rows, if single-model accuracy proves insufficient.
  - Dropped: superseded by extraction voting — see spec.md, Extraction (Voting,
    not escalation).
- [ ] Multi-format sheet geometry: support two-column scoresheet layouts (the
      Baron Barclay and Bridge Buddy samples in `bridge-private/scoresheets`).
      Not a detection tweak — needs column-grid segmentation before row
      detection, `SheetGeometry` reshaped as multiple grids with per-grid row
      counts (Baron Barclay prints 16 rows left, 20 right), strip labels that
      carry column identity, and exclusion of the printed VP/IMP scale tables,
      which are themselves uniform grids that pollute the row-count vote.
  - Note: the user keeps a sheet at tournaments (ACBL-only sessions), played on
    non-club forms, so multi-format support has a concrete driver beyond the
    sample forms — see spec.md (Scope).
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

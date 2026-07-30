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
- [ ] Re-run the strips comparison against `claude-opus-5` and update spec.md's
      cost delta and quality notes.
  - Rationale: `DEFAULT_MODEL` moved from `claude-opus-4-8` to `claude-opus-5`;
    the recorded ~$0.25–0.30/run figure and the markup-reading comparison were
    measured against the old model and may no longer hold.

---

## Reconciliation

**Goal:** capture the travellers as a game-record database and join them to the
digitized sheet — enriching it with the deal, matchpoints, and pair identities,
and surfacing disagreements and row swaps. Design in
[travellers.md](travellers.md).

- [ ] Traveller data model — `Traveller`/`TravellerBoard`/`TravellerResult`,
      plus the shared `Deal`/`Hand`/`PairIdentity` canonical types (see
      models.md). Replaces the `Source.travellers` placeholder (`tuple[str]`).
  - Note: the par shape is settled — see travellers.md (Double-dummy par).
- [ ] ACBL Live HTML parser → full traveller (every row, deal, par).
  - Note: par appears twice in the capture — rendered in the markup under
    `div.par-score`, and again in an embedded JSON blob the page appears to
    render from. The blob is likely the easier parse: it carries the value as
    plain text, where the rendered form spells each suit as an
    `<i class="fa spades">` glyph. Par reads `-450 4S-EW+1/4H-EW+1` — score
    first, `/` between multiple contracts (escaped `\/` inside the JSON), `*`
    for a double (`3D*-NS-1`), and a declarer that is a side (`-EW`) or a seat
    (`-E`).
  - Note: two ACBL surfaces, two formats. The above is the club capture
    (my.acbl.org, the `var data` blob). A tournament summary (live.acbl.org,
    which `acbl_fetching` saves) instead renders its boards into HTML tables
    with no such blob, so the parser needs a distinct reader for each.
- [ ] Club PBN parser → full traveller (every row, deal, par, double dummy). The
      easier of the two club formats, and the one to build first — see
      travellers.md (Which club format to parse).
- [ ] Club site HTML parser → full traveller (every row, deal, par). Still
      needed: roughly a sixth of games publish no PBN.
  - Note: par renders as `Par −1430: E 6♦=`, with a Unicode minus (U+2212), not
    an ASCII hyphen, and `&nbsp;` between the parts. Suits are glyphs carrying a
    CSS class (`bcspades`), so suit identity comes from the class, not the
    character. Declarer is a side (`EW`) or a seat (`E`), as with ACBL.
  - Note: has to read both the `R` and `C` variants, and both raw and
    browser-saved markup — see travellers.md (Which club format to parse).
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

- [ ] Read traveller captures through a configurable path.
  - Note: the captures now live in `bridge-private/travellers/`, moved out of
    the public repo and left uncommitted there pending a storage decision — the
    ACBL `_files` bundle is 3.4 MB of the 4.7 MB total. `club_fetching.py` takes
    its download destination as an argument, so this task is what gives the
    fetcher and the parsers a single configured location to share.
- [ ] Match a capture to its session by parsed metadata (event + date), not the
      filename or URL.
  - Note: the club calendar's label for a game (`Palo Alto Duplicate`) is not
    the event name inside its files (`John & Will's Monday Bridge`), so the
    label can't stand in for the metadata.
- [ ] Manual-save fallback: a capture dropped in is picked up and matched.
- [ ] Verify the ACBL club index isn't truncated for older dates.
      `fetch_club_travellers` reads the index via an in-page fetch of the raw
      server HTML, which returned every row for the tournament index (not just
      the DataTables-visible page); the club index uses the identical mechanism,
      so it is expected to hold — but only a recent, top-of-list club date was
      checked. Fetch an older club date and confirm the game is found.
- [ ] Auto-reconcile: a fetched traveller matching a pending session triggers
      reconciliation; review stays deferred until then.
- [ ] Escape hatch: an explicit "finalize without traveller" action for a
      session no traveller arrives for.
- [ ] Store parsed travellers as structured JSON; keep raw HTML lean (drop the
      ACBL `_files` asset bundle).

---

## Ingest

**Goal:** get a scan from the phone onto the Mac and through the pipeline — the
first stage that runs extraction end to end and writes a session to disk.

- [ ] Choose the scanner app and transport.
  - Open question: Android scanner + Drive-mirror vs. Syncthing — see spec.md
    (Open questions) and the Ingest section's tradeoffs.
  - Note: this gates where `inbox/` lives, not the pipeline code below it — the
    spine can be built and tested against a local directory first.
- [ ] Settle the ingest tree's home and reach it through a configured root:
      `inbox/`, `archive/`, and the `processed/` records.
  - Rationale: scans and reconciled sessions carry other members' names, so the
    tree belongs in `bridge-private` alongside `scoresheets/`, not in this repo
    under a relative path.
  - Note: the traveller captures need the same treatment (see Traveller
    acquisition) — decide the two together so they share one setting, or two
    that agree.
- [ ] Wire the extraction run: scan image → `transcribe_sheet` →
      `parse_and_assemble_voted_session` → a validated `Session`. Nothing calls
      the two entry points together today.
  - Note: ingest supplies what they need beyond the image — the `Source`
    (archived path plus content hash) and the `reference_date`.
  - Note: `reference_date` is the day of the scan, not the day of the run — it
    is what fixes the year on a footer that writes only `6/29`. Reprocessing an
    archived scan resolves the year against the wrong "today" and shifts it
    silently, so take the date from the image's capture time, not the clock.
- [ ] Decode the scan into images: rasterize PDF pages, and settle what several
      pages in one container mean.
  - Open question: spec.md allows a multi-page scan of one sheet, but
    `transcribe_sheet` takes a single image. Are the extra pages retakes to
    choose among, parts of one grid to stitch, or separate sheets? The answer
    decides whether this is a decode step or a merge stage.
- [ ] Persist the detected geometry and `source_quad` with the processed
      session.
  - Note: `SheetTranscription`'s docstring already promises these persist
    "alongside the processed session", so the review UI can reproduce the
    dewarped frame and its grid from the archived scan instead of re-detecting
    them — but `Session` and `Source` have no field to hold them. Needs a
    models.md decision before the writer lands.
- [ ] Failure disposition: a scan that raises — `SheetGeometryError`, an
      unreadable file, a failed model invocation — reports loudly and moves
      somewhere terminal rather than sitting in `inbox/` for the next run to
      retry.
  - Rationale: the explicit command was chosen over a watcher so failures stay
    visible; a scan that silently stays put re-spends a model call every run.
- [ ] Inbox spine: `inbox/` → `processed/<session-key>.json` + image →
      `archive/`, idempotent on footer + content hash.
  - Note: the two keys apply at different points. The content hash is known
    before extraction and short-circuits a re-dropped file without spending a
    model call; the footer is known only after extraction, and catches a fresh
    photo of a sheet already digitized.
- [ ] Footer self-naming → session key, confirmed in review before commit.
  - Note: derivation is unspecified beyond the example `pabc-mon-2026-06-29` — a
    club slug and a weekday off handwritten freetext, so it needs a
    normalization rule rather than a format string.
  - Note: the key is also the reconciliation join, so it has to agree with the
    traveller-side match on event and date (see Traveller acquisition).
  - Open question: review is deferred until reconciliation runs, so the key
    can't be confirmed at ingest time. Decide what the record and its image are
    named in between — a provisional key renamed once confirmed, or a stable id
    that never moves, with the key as a field only.
- [ ] The "process inbox" command.
  - Note: `session_analysis` is a `package = false` uv member with no console
    script, so this runs as `python -m session_analysis.<module>` unless that
    changes; `convention_cards/make_card.py` is the house argparse pattern.
  - Note: an explicit trigger only beats a watcher if its output says what
    happened — summarize each scan as digitized, skipped, or failed.

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

---

## Cleanup

**Goal:** tidy-ups that only make sense once the work they trail has landed.

- [ ] Drop the `session_analysis/travellers/` entry from `.gitignore`. The
      directory is gone — the captures live in `bridge-private` now — and the
      entry is kept only as a guard while the traveller code is in flight, in
      case a fetch or parser defaults to writing back into the public repo.
      Remove it once acquisition and the parsers read a configured path.
- [ ] Reorganize the raw captures under `bridge-private/travellers/raw/` by date
      rather than by source. Both fetchers currently mirror each source's own
      path (`live.acbl.org/event/…`, `my.acbl.org/club-results/…`,
      `gameresults2/…`); a date-first layout would group a session's captures
      across sources together. Decide the scheme (e.g. `<date>/<source>/…`) and
      migrate the existing captures.
- [ ] Mine the parked `traveller-model` worktree for anything still worth
      keeping, then delete the branch and its worktree. Sequenced last: it only
      makes sense once the traveller work it overlaps has all landed.
  - Note: it holds a second, earlier traveller data model, superseded by the one
    real captures drove. Its documentation fixes were already folded in; what
    may remain is the `TravellerIdentity` shape (worth a look when the storage
    task settles what a traveller reference is) and the `Board` enrichment
    fields `deal`/`our_pair`/`opponents`, which models.md documents and the
    reconciliation phase will need.

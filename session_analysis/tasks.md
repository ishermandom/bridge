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
  - Note: this subsumes re-measuring the full-sheet side of spec.md's
    strips-versus-full-sheet cost figures, which are still Sonnet-era. Whether a
    whole-sheet read works at all is the question worth answering; its price
    alone is not.
- [ ] Decide whether the two-run vote still earns its keep on Opus 5.
  - Rationale: the refreshed strips comparison found Opus 5's two runs agreeing
    completely on the 6/29 sheet — the pass flags nothing, and the errors that
    remain are made identically by both runs, so it cannot flag them either. On
    that sheet the second run buys nothing for about a third of the per-sheet
    cost. One sheet is thin evidence to drop a safety net on, so this wants a
    second sheet before deciding.
  - Note: measurements and the limitation are in spec.md #extraction-voting;
    `scratch/README.md` covers re-running them on a second sheet.

---

## Reconciliation

**Goal:** capture the travellers as a game-record database and join them to the
digitized sheet — enriching it with the deal, matchpoints, and pair identities,
and surfacing disagreements and row swaps. Design in
[travellers.md](travellers.md).

The traveller data model, the shared notation, scoring, and all four capture
parsers have landed on `main`, each verified against the real captures. What
remains is the join to the sheet.

- [ ] Replace the `Source.travellers` placeholder (`tuple[str, ...]`) in
      models.py with a reference to the stored traveller.
  - Worktree: reconciliation-join
  - Note: a stored traveller is named by its `CaptureReference.path` — the
    capture's path under the capture root, which is also where its record sits
    with `.json` appended. Whether the sheet's `Source` should hold that path or
    the record's own is what remains open here.
- [ ] Find our row by the configured name — either direction, any partner; flag
      when the name is absent. {#our-row}
  - Worktree: reconciliation-join
  - Note: ACBL carries a player number per player, which the parsers keep
    nowhere — `PairIdentity` holds names only. It would be a far stronger key
    than a name for the ACBL sources, and it is the one identity the club's
    files do not carry; worth weighing here against the name-variant problem it
    would sidestep.
  - Open question: how well the name match holds on a row carrying surnames
    alone. The two full-name lookups differ on the movements that number every
    pair once: `acbl_club_parsing` falls back to a direction-agnostic
    `(None, number)` key, where `club_html_parsing` has nothing equivalent — see
    #one-winner-recap for what that costs and why it is parked.
- [ ] Cross-check recoverable fields; raise review priority on disagreement.
  - Worktree: reconciliation-join
  - Note: the declarer is cross-checked here — the validator can't (an auction
    with implicit passes gives no seats), and neither sheet nor traveller is
    authoritative, so surface the disagreement rather than trusting either side.
- [ ] Merge the two sources; flag disagreements, store both raw records, no
      silent tiebreak.
  - Worktree: reconciliation-join
  - Note: a club game's PBN comes in two kinds, and a board-count difference
    between a session's two captures is usually that rather than a disagreement.
    `watson/D260714M.pbn` carries twenty result rows per board;
    `lagcc/D260717A.pbn` and `vi/D260714A.pbn` carry none at all — they are hand
    records, listing every board dealt (always 24) with no play. Their HTML
    recaps cover the boards actually played, 15 and 20. So merging should take
    the deal from whichever capture has it and the results from whichever
    played, and treat a dealt board carrying no results as a board not reached
    rather than as a source disagreeing.
- [ ] Deal capture + the deal-versus-lead check (opening lead ∈ declarer's LHO
      hand) and deal well-formedness (52 distinct cards, 13 per hand).
  - Worktree: reconciliation-join
- [ ] Best-alignment permutation swap detection — suggest, never auto-apply.
      Test against the 6/29 board-20/21 swap.
  - Worktree: reconciliation-join
- [ ] Graceful degradation: run to completion with zero travellers (no deal, no
      enrichment).
  - Worktree: reconciliation-join

---

## Traveller acquisition

**Goal:** get travellers into the pipeline — auto-fetch where possible, manual
save otherwise — and auto-reconcile when one lands. Design in
[travellers.md](travellers.md#acquisition).

- [ ] Match a capture to its session by parsed metadata (event + date), not the
      filename or URL.
  - Worktree: ingest-spine
  - Note: the club calendar's label for a game (`Palo Alto Duplicate`) is not
    the event name inside its files (`John & Will's Monday Bridge`), so the
    label can't stand in for the metadata.
- [ ] Manual-save fallback: a capture dropped in is picked up and matched.
  - Worktree: ingest-spine
- [ ] Verify the ACBL club index isn't truncated for older dates.
      `fetch_club_travellers` reads the index via an in-page fetch of the raw
      server HTML, which returned every row for the tournament index (not just
      the DataTables-visible page); the club index uses the identical mechanism,
      so it is expected to hold — but only a recent, top-of-list club date was
      checked. Fetch an older club date and confirm the game is found.
  - Note: the index walk returns all 29 rows, the oldest a year back, so the
    reading is not truncated. What is left to confirm is the fetch of an old
    row's game page.
- [ ] Notice when a club fetch lands on the login page rather than a game. Three
      of the games listed on the club index answer a fetch that has already
      cleared Cloudflare with an `ACBL Login` page, which the fetcher saves as
      the capture. `acbl_club_parsing` then reports `no_page_data`, so nothing
      goes silently wrong downstream, but a login page is not worth keeping as a
      capture.
  - Note: reproducible in a signed-out browser at
    `my.acbl.org/club-results/details/1430431`, and kept under
    `bridge-private/session_analysis/travellers/raw/acbl_club/`. The site
    redirects rather than serving the login page outright — the first fetch dies
    with Playwright's "Execution context was destroyed" and the retry lands on
    the redirect target.
  - Open question: what makes a game gated. Not the club — `1438869` is gated
    and `1441256` is not, both at Palo Alto Duplicate. A game can have more than
    one director and they do not always upload alike, so which director
    published it is the first thing to look at.
- [ ] Auto-reconcile: a fetched traveller matching a pending session triggers
      reconciliation; review stays deferred until then.
- [ ] Escape hatch: an explicit "finalize without traveller" action for a
      session no traveller arrives for.

---

## Ingest

**Goal:** get a scan from the phone onto the Mac and through the pipeline — the
first stage that runs extraction end to end and writes a session to disk.

- [ ] Choose the scanner app and transport.
  - Open question: Android scanner + Drive-mirror vs. Syncthing — see spec.md
    (Open questions) and the Ingest section's tradeoffs.
  - Note: this gates where `inbox/` lives, not the pipeline code below it — the
    spine can be built and tested against a local directory first.
- [ ] Wire the extraction run: scan image → `transcribe_sheet` →
      `parse_and_assemble_voted_session` → a validated `Session`. Nothing calls
      the two entry points together today.
  - Worktree: ingest-spine
  - Note: ingest supplies what they need beyond the image — the `Source`
    (archived path plus content hash) and the `reference_date`.
  - Note: `reference_date` is the day of the scan, not the day of the run — it
    is what fixes the year on a footer that writes only `6/29`. Reprocessing an
    archived scan resolves the year against the wrong "today" and shifts it
    silently, so take the date from the image's capture time, not the clock.
- [ ] Decode the scan into images: rasterize PDF pages, and settle what several
      pages in one container mean.
  - Worktree: ingest-spine
  - Open question: spec.md allows a multi-page scan of one sheet, but
    `transcribe_sheet` takes a single image. Are the extra pages retakes to
    choose among, parts of one grid to stitch, or separate sheets? The answer
    decides whether this is a decode step or a merge stage.
- [ ] Persist the detected geometry and `source_quad` with the processed
      session.
  - Worktree: ingest-spine
  - Note: `SheetTranscription`'s docstring already promises these persist
    "alongside the processed session", so the review UI can reproduce the
    dewarped frame and its grid from the archived scan instead of re-detecting
    them — but `Session` and `Source` have no field to hold them. Needs a
    models.md decision before the writer lands.
- [ ] Failure disposition: a scan that raises — `SheetGeometryError`, an
      unreadable file, a failed model invocation — reports loudly and moves
      somewhere terminal rather than sitting in `inbox/` for the next run to
      retry.
  - Worktree: ingest-spine
  - Rationale: the explicit command was chosen over a watcher so failures stay
    visible; a scan that silently stays put re-spends a model call every run.
- [ ] Inbox spine: `inbox/` → `processed/<session-key>.json` + image →
      `archive/`, idempotent on footer + content hash.
  - Worktree: ingest-spine
  - Note: the two keys apply at different points. The content hash is known
    before extraction and short-circuits a re-dropped file without spending a
    model call; the footer is known only after extraction, and catches a fresh
    photo of a sheet already digitized.
- [ ] Footer self-naming → session key, confirmed in review before commit.
  - Worktree: ingest-spine
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
  - Worktree: ingest-spine
  - Note: `session_analysis` is a `package = false` uv member with no console
    script, so this runs as `python -m session_analysis.<module>` unless that
    changes; `convention_cards/make_card.py` is the house argparse pattern.
  - Note: an explicit trigger only beats a watcher if its output says what
    happened — summarize each scan as digitized, skipped, or failed.

---

## Review UI {#review-ui}

**Goal:** a minimal, standalone tool to correct flagged fields, image beside
parsed value.

- [ ] Choose the tech (FastAPI + htmx, or Gradio).
  - Worktree: review-ui
  - Open question: framework, keybindings, commit semantics — see spec.md
    `#open-questions`.
- [ ] Triage-ranked field list with image crop beside the parsed value and
      keyboard accept/fix.
  - Worktree: review-ui
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
  - Note: not every issue belongs to a board or a field. `store_travellers`
    reports run-level ones — a capture no parser claims, a page that held no
    boards — which have no board to hang on and no image to crop beside, since
    they are about a file rather than a scoresheet row. Triage needs somewhere
    to show them, or they reach nobody.
- [ ] Row-level fixups (swap, renumber, reorder) as first-class operations.
  - Worktree: review-ui
- [ ] Re-validate after edits; auto-open or notify after a sheet is processed.
  - Worktree: review-ui
  - Note: `validate_board` appends freshly found issues onto `board.issues`
    unconditionally, with no de-duplication. Re-validating the same board twice
    (an edit that didn't touch the flagged field, or a retry) will accumulate
    duplicate `Issue` entries unless this task also strips prior
    validation-origin issues before re-running the checks.

---

## Backlog

Forward-looking items parked until their phase or trigger arrives; their
rationale lives in the design docs' open-question sections —
[spec.md](spec.md#open-questions),
[travellers.md](travellers.md#open-questions), and
[models.md](models.md#open-questions-and-todos).

- [ ] Final storage format (queryable DB) and the JSON → DB migration.
  - Note: the canonical models store cards as `Card` objects for uniformity and
    for the in-memory checks. That is roughly an order of magnitude larger than
    the bridge-standard packed form (a hand as `AKQJ.T98.765.432`), and pairs
    are stored inline per row rather than through a session-level roster. Both
    are compactness tradeoffs to weigh when the durable store is designed; they
    do not matter for the transitional JSON.
- [ ] Fix what an ACBL hand record with no double-dummy analysis produces.
      Trigger: a capture with one, or a decision to harden regardless.
      {#acbl-absent-double-dummy}
  - Note: `acbl_notation.double_dummy_tricks` given empty analysis strings
    returns a table of twenty nulls rather than None, which misreports "no
    analysis published" as "analysis published, every cell unknown" —
    `TravellerBoard.double_dummy_tricks` documents None as the former. That is
    the whole of what remains here: a sentinel that lies about which case it is
    in, needing a capture only to confirm what such a record looks like.
  - Note: `club_pbn_parsing._makeable_tricks` settles the same question the
    other way for its own source — a table with no readable rows at all comes
    back as None, not as an empty mapping — so follow it here.
- [ ] Report the scalar fields a capture states unreadably, instead of passing
      them off as unstated. Trigger: a capture that exercises one, or a decision
      to harden regardless. {#silent-none}
  - Note: every parser has a `_number`, `_date`, or `_integer` helper that
    returns None for anything it cannot parse — roughly ten `except ValueError:`
    sites across `club_pbn_parsing`, `club_html_parsing`, `acbl_club_parsing`,
    and `acbl_tournament_parsing`. So a mangled date, score, or matchpoint
    arrives as "the source said nothing", which is the one thing
    `TravellerResult.issues` says it must not be.
  - Note: the reason they are lenient is that each field has a legitimate
    absence spelled in-band, and none of these helpers can tell that absence
    from garbage: an empty field and `??` for a PBN date, `-` for a numeric
    cell. The fix is the shape `club_pbn_parsing._board_from_record` already
    uses for the dealer — match the source's own absence markers first, then
    report whatever is left over.
  - Note: every captured file reads cleanly, so nothing exercises the path
    today. Hardening blind would turn a format change into noise rather than a
    signal, which is why this waits on a trigger.
  - Note: the tournament captures name their two in-band absence markers
    already, so that parser's `_integer` has the concrete list to match against
    when the time comes: `PASS` for a passed-out board and `NS` for a row with
    no result. The same pass should drop that helper's comma stripping, which no
    score in either capture exercises.
  - Open question: what ACBL means by the `NS` a resultless row carries. Across
    858 rows it appears 34 times and `EW` never, always beside a blank contract
    and declarer, zero matchpoints, and a score-correction link reading
    `recordedContract=+&score=NS` where a played row carries a number. The code
    describes what the page does and expands nothing, which is settled; the
    reading itself stays open, and a capture carrying `EW` would answer it.
- [ ] Recover full names from a one-winner club recap. Trigger: a captured
      Howell or other one-winner movement. {#one-winner-recap}
  - Note: `club_html_parsing` reads the standings recap only after a heading
    naming a direction (`Section A North-South`). A one-winner movement ranks
    its pairs as a single list, so its recap plausibly heads the standings with
    the section alone — and that parser would then collect no standings at all,
    leaving every pair with the surnames its board row prints. Confirmed by
    stripping the direction from a fixture: no row is lost and nothing raises,
    but the full names go.
  - Open question: what such a heading actually says. Every club capture on hand
    is a two-winner Mitchell, so the fix cannot be written without guessing at
    the markup — hence parked rather than attempted.
- [ ] Remote-backed, size-tolerant durable store beyond `bridge-private`, if the
      growing game database outgrows the repo.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller — they carry the deal, too.
- [ ] Pianola as a traveller source, for club games that post only there
      (deferred: the sessions currently played don't use it).
- [-] Model escalation: a stronger-model fallback for low-confidence auction
  rows, if single-model accuracy proves insufficient.
  - Dropped: superseded by extraction voting — see spec.md `#extraction-voting`.
- [ ] Multi-format sheet geometry: support two-column scoresheet layouts (the
      Baron Barclay and Bridge Buddy samples in
      `bridge-private/session_analysis/scoresheets/samples`). Not a detection
      tweak — needs column-grid segmentation before row detection,
      `SheetGeometry` reshaped as multiple grids with per-grid row counts (Baron
      Barclay prints 16 rows left, 20 right), strip labels that carry column
      identity, and exclusion of the printed VP/IMP scale tables, which are
      themselves uniform grids that pollute the row-count vote.
  - Note: which layout a session used follows from which sheet was to hand — the
    custom single-column form, or a double-column one provided at the venue —
    and not from the kind of event. Club games and tournaments both turn up
    either way, so this is a live driver rather than a sample-only concern. See
    spec.md `#scope`.
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
- [ ] Maybe: solve the traveller fixtures' double-dummy numbers rather than
      writing them by hand. Every fixture's deals are legal and each par matches
      a contract its own analysis states, but nothing checks that the trick
      counts are what the deal actually yields. Applies to every capture
      fixture, not the club HTML pair alone.
  - Rationale: someone who solves a fixture deal finds it disagrees with the
    analysis printed beside it, which reads as a parser bug until they check.
    Nothing is wrong today — no parser compares the two.
  - Note: would need a double-dummy solver, which the project does not depend
    on, so the real question is whether to take one on for test data alone.
  - Note: the ACBL and PBN fixtures were generated by throwaway scripts that
    also assert the matchpoint arithmetic — every row's two awards summing to
    the top, and each side's awards to the same total. The scripts were not
    kept; regenerating one means rewriting it, so prefer editing a fixture in
    place unless the change is wholesale.
- [ ] Maybe: teach the PBN reader what a `{}` comment block is. `_read_records`
      ignores one only because no table tag is open while it runs — a block
      placed after a table tag would have its lines read as that table's rows.
  - Rationale: every capture puts its `{}` block in the opening game, ahead of
    any table, so nothing is wrong today. The tolerance is incidental rather
    than intended, which is the part worth fixing or writing down.
  - Open question: fix, or leave the tolerance and record the assumption in
    `_read_records`?
- [ ] Revisit the open questions in
      [models.md](models.md#open-questions-and-todos) as their triggering work
      lands — each is a design decision deferred to the phase that resolves it.
      Resolve or re-defer each rather than letting the section rot.

---

## Cleanup

**Goal:** tidy-ups that only make sense once the work they trail has landed.

- [ ] Drop the `session_analysis/travellers/` entry from `.gitignore`. The
      directory is gone — the captures live in `bridge-private` now — and the
      entry is kept only as a guard while the traveller code is in flight, in
      case a fetch or parser defaults to writing back into the public repo.
      Remove it once acquisition reads a configured path; the parsers no longer
      need the guard, since they take a capture's contents and write nothing.
  - Note: that precondition is met — `private_paths` locates the private
    checkout and nothing writes into the public repo — so this is ready to do.
  - Note: the entry names a directory, so it does not touch the
    `session_analysis/travellers.py` module beside it. Worth confirming when the
    entry goes, since the two names differ only by the trailing slash.
- [ ] Reorganize the raw captures under
      `bridge-private/session_analysis/travellers/raw/` by date rather than by
      site. They sit under a directory per publishing site, each mirroring that
      site's own path beneath it; a date-first layout would group a session's
      captures across sites together. Decide the scheme (e.g. `<date>/<site>/…`)
      and migrate the existing captures.
  - Note: the site directory is what picks a capture's parser, so it has to stay
    a path component wherever the captures land. A capture's `.url` sidecar has
    to move with it, which moving a whole directory does for free — but a
    migration that renames files one at a time has to carry the sidecar along,
    since the URL is the one piece of provenance nothing can recover afterwards.
- [ ] Mine the parked `traveller-model` worktree for anything still worth
      keeping, then delete the branch and its worktree. Sequenced last: it only
      makes sense once the traveller work it overlaps has all landed.
  - Note: it holds a second, earlier traveller data model, superseded by the one
    real captures drove. Its documentation fixes were already folded in; what
    may remain is the `TravellerIdentity` shape (now comparable against the
    `CaptureReference` the storage work settled on) and the `Board` enrichment
    fields `deal`/`our_pair`/`opponents`, which models.md documents and the
    reconciliation phase will need.

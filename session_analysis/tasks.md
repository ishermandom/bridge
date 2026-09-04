# Session analysis — digitization tasks

Implementation tracker for the scoresheet digitization pipeline. Design and
rationale live in [spec.md](spec.md), [models.md](models.md), and
[travellers.md](travellers.md); this file tracks work, not decisions.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

The phases follow the spec's build order: the pure-logic core first (zero OCR,
fully testable, de-risks everything downstream), then extraction, the traveller
subsystem (parsing, reconciliation, acquisition), ingest, and the review UI.

---

## Pending review

**Goal:** drain the deferred-review queue, so that nothing on `main` stays
unread.

- [ ] Review each module under `session_analysis/unreviewed/` and move it up
      into `session_analysis/` with its test beside it.
  - Note: the directory is the queue — it lists itself, so nothing here names
    the modules and nothing can fall out of step with what is actually pending.
    `unreviewed/__init__.py` covers what the directory means and what leaving it
    takes.
  - Note: two `/code-review high --fix` rounds have already run over the
    reconciliation join, so the automated sweep is done and what is left is
    judgment. Both rounds' remaining findings are TODOs at the lines they
    concern.
  - Note: eighteen `/code-review high` rounds then ran over the change that had
    the model read the sheet's layout, converging: the last found no correctness
    defect. Weight the tail lightly — rounds twelve to seventeen each found
    defects mostly in the previous round's fix rather than in the change, and
    three times a proposed tightening would have broken real pages, which
    measurement caught. The thresholds in `rule_grid` and `sheet_geometry` carry
    their measurements in comments for that reason; read those before retuning
    any of them.
  - Note: five more such rounds ran over the auto-reconcile join, and the first
    four each found a real defect in the previous round's fix — all in the rule
    deciding whether a session's enrichment stands. The rule is worth reading on
    its own terms rather than trusting the round count: a capture is withdrawn
    when its file is gone, and a capture still on disk that a run placed nowhere
    holds the session rather than rejoining it.
  - Note: `ingest` now drives three stages — the scans, the capture matching,
    and the join — and has grown to around 760 lines. Keeping the join there
    rather than in a module of its own was settled with the user, but on a
    smaller expected addition than it turned out to be, so the split is worth
    weighing again at review.
  - Note: the design is settled — the `CaptureReference` on `Source`, matching
    our row on the configured full name and its surname, leaving the ACBL player
    number uncarried, leaving a disputed field unfilled, searching
    transpositions for swaps, keeping the declarer out of that search, and
    rewriting the findings a run owns. All were put to the user and agreed, so
    what remains is whether the code does what those decisions say, not whether
    the decisions were right. Each is argued where it is implemented;
    #disagreement-in-practice and #swap-detection-in-practice revisit two of
    them against real sessions rather than in review.
  - Note: `scratch/reconciliation_against_captures.py` re-runs the join over the
    real captures, which is the evidence the fixtures cannot give.
  - Note: the acquisition command's shape was likewise settled with the user
    before it was written — a required `--player-number` rather than a
    configuration file, every source fetched by default with `--source` to
    narrow, a failed source reported and stepped over rather than aborting the
    run, and a nonzero exit when one fails. The player number stayed a flag
    because the shared configuration
    [travellers.md](travellers.md#configuration) wants did not exist yet;
    auto-reconcile has since built it, so repointing the flag at it is the
    tracker item below rather than an open question.
  - Note: that command has run against the live sites, not only against its test
    double. Its first run, on 2026-08-24, stored both club captures while both
    ACBL sources failed on Cloudflare, which exercised the failure-containment
    path for real; after the ACBL fetch was reworked, the same date fetched all
    three sources in about fifteen seconds. Both paths have therefore been seen
    end to end.
  - Note: expect the ACBL fetch to be uneven rather than instant. Cloudflare's
    challenge is sometimes harder, and a run that draws one waits out the full
    sixty seconds before retrying on a fresh tab, which the warning line names.
    A minute-long run that ends in captures is working, not stuck.
  - Note: the queue is seven modules and about 4,700 lines with their tests,
    having gone from three to seven in one session — and it is meant to keep
    growing for now. Deferring review is a deliberate tactic while the pipeline
    is being taken end to end for the first time, so a session that finds the
    queue long should keep building rather than stop to drain it. The count is
    here to be watched, not yet acted on.
  - Note: when draining does start, the spine's four — `ingest`,
    `scan_decoding`, `session_keys`, and `session_matching` — were written in
    one session and read fastest as one sitting.
  - Note: the ingest spine — `ingest`, `scan_decoding`, `session_keys`, and
    `session_matching` — landed the same way. Its design was settled with the
    user before it was written: the frame on `SheetImage` rather than `Source`,
    a provisional key renamed at review rather than a stable id, the key derived
    from the footer alone with the time of day riding in the footer text, the
    capture match reading the date alone, every page of a scan container
    digitized as its own sheet, and failures moved to `scoresheets/failed/` with
    a sidecar. Each is argued where it is implemented, so what remains is
    whether the code does what those decisions say.
  - Note: the spine has now been run against real scans, which answered three
    things the tests could not:
    - A phone scan needs almost no dewarping — Google's ML Kit scanner rectifies
      and crops before writing the PDF.
    - The file states the day it was taken, in the PDF's own `/CreationDate`.
    - A real footer normalizes as expected: `PABC mon.` on 8/31 gives
      `pabc-mon-2026-08-31`.
  - Open question: whether `reconciliation.py` wants splitting. At 1076 lines it
    is the project's longest module, though only a little past
    `club_html_parsing.py`, so it is a judgment call rather than a clear
    problem. Merging the sources apart from joining them to the sheet is the
    seam that was considered and left alone while the two were being written
    together; review is the moment to settle it.

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

## Reconciliation ✓

**Goal:** capture the travellers as a game-record database and join them to the
digitized sheet — enriching it with the deal, matchpoints, and pair identities,
and surfacing disagreements and row swaps. Design in
[travellers.md](travellers.md).

The join is `unreviewed.reconciliation.reconcile_session`, taking the sheet,
every traveller covering it, and the configured player name;
`unreviewed.deal_checks` holds the deal and opening-lead integrity checks.
Deciding which travellers cover a session belongs to acquisition, below.

---

## Traveller acquisition

**Goal:** get travellers into the pipeline — auto-fetch where possible, manual
save otherwise — and auto-reconcile when one lands. Design in
[travellers.md](travellers.md#acquisition).

`fetch_travellers` drives a date's fetch and the store pass that follows it, and
`unreviewed.session_matching.match_travellers` places each stored capture
against the sessions on hand, reading the capture's date alone — travellers.md
`#matching` covers why an event name cannot be compared across sources. The
ingest command runs both on its way past and then joins each pending session to
the travellers now covering it, as
`unreviewed.ingest.reconcile_pending_sessions`. So neither a capture saved by
hand nor the reconciliation a match sets off needs a command of its own.

Every ACBL fetch needs a desktop session of this account's own to launch its
browser into, which a session started through the ssh `claudify` has and an
older one does not. The club capture route needs no browser at all, so a run
that returns club captures and no ACBL ones may be reporting the environment
rather than a fault.

- [ ] Fetch a real tournament traveller through the reworked ACBL fetch.
      Trigger: the next tournament played.
  - Rationale: the rework is proven end to end on the club surface — index, game
    page, stored record — but the tournament surface has only ever been read as
    far as its index, because no tournament fell on the date used to validate
    it. The two surfaces share their machinery, so this is confirmation rather
    than suspicion.
- [ ] Stop the two unstorable ACBL captures reporting themselves every run.
  - Rationale: `1430431` is a saved login page and `1484015` a team game, so
    neither ever parses to boards and neither ever gets a record. Every run
    therefore ends with the same two `capture_held_no_boards` issues, and always
    will. It is why `has_fetch_failures` ignores issues, which is a workaround
    for the noise rather than an answer to it.
  - Open question: whether to file such captures somewhere the store does not
    walk, record that they are known, or teach the store to say "known, still
    nothing" more quietly. Deleting them would lose the two examples the
    parsers' tests describe.
- [ ] Share one browser across a run's two ACBL surfaces.
      {#share-one-acbl-browser}
  - Rationale: `fetch_club_travellers` and `fetch_tournament_travellers` each
    build a `_BrowserFetcher` of their own, so a run that fetches both launches
    two browsers and clears two challenges. The 8/24 run shows it plainly —
    "browser up" twice, on ports 55907 and 55955.
  - Note: the cost is about five seconds of a fifteen-second run, so this is
    tidiness rather than a problem. Fixing it means making `_BrowserFetcher`
    public so the command can open one and hand it to both surfaces; weigh that
    widening against what it saves.
- [ ] Disambiguate a capture matching two sessions. {#multi-session-days}
  - Rationale: a two-game day leaves a club capture matching both sessions.
    `match_travellers` reports the ambiguity and matches neither rather than
    guessing, so nothing goes silently wrong — but it does leave a manual step.
  - Note: only the ACBL club surface publishes anything time-like today, as a
    coarse `club_session` label (`Monday Morning`); the club's own PBN and HTML
    and the ACBL tournament pages carry a date and nothing finer. Tournament
    captures are expected to state a session time, which is the first thing to
    check.
  - Note: the strongest signal available may be our-row name matching — we
    appear in the traveller for the session we actually played — and the
    configured name that needs is now on hand, in `unreviewed.configuration`.

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
- [ ] Escape hatch: an explicit "finalize without traveller" action for a
      session no traveller arrives for.

---

## Ingest

**Goal:** get a scan from the phone onto the Mac and through the pipeline — the
first stage that runs extraction end to end and writes a session to disk.

The spine is `unreviewed.ingest.process_inbox`, run as
`python -m session_analysis.unreviewed.ingest`: `scan_decoding` reads a scan
file into an image and the day it was taken, `unreviewed.ingest.digitize_scan`
carries it through extraction and assembly, and `session_keys` names the result
from its footer. The run also stores newly saved traveller captures and matches
them. spec.md `#ingest` holds the shape — the two idempotency keys, where a
record waits for review, and what becomes of a scan that raises.

- [ ] Give the dewarp the row count too, rather than voting for it.
      {#dewarp-needs-the-reading}
  - Rationale: `dewarp_sheet` still calls `resolve_grid_consensus`, which is the
    row-count vote the geometry stage stopped using. It runs before
    `read_sheet_structure`, so a sheet the vote refuses never reaches the model
    at all — and a two-panel form whose panels differ in height is exactly what
    it refuses, since the slices then split between two counts and the tie-break
    wants both readings to share a bottom rule. Bridge Buddy dewarps (its panels
    are the same height); Baron Barclay does not.
  - Note: the dewarp's bottom margin is the same assumption in another place. It
    keeps three row pitches below the grid's last rule, which is where the
    footer sits on the forms in hand — but `read_sheet_structure` reads the
    dewarped frame, so a form printing a chart between the table and its footer
    has that footer cropped away before the model can report it. The sheet then
    digitizes, files unnamed, and says only that the footer was unreadable.
    Reading the raw scan closes this too.
  - Note: the quad itself should stay measured. It comes from four least-squares
    line fits over ~40 observations, and a homography is exactly determined by
    its corners, so a reported corner's error would bend the whole page — the
    opposite of the row count, where the reading is the reliable half.
  - Note: removing `resolve_grid_consensus` takes three test files with it.
    `extraction_test`, `ingest_test`, and `sheet_dewarp_test` each call it to
    work out where a drawn grid lands in the dewarped frame, standing in for the
    reading a real run gets from the model. They want a replacement stand-in
    before the function goes.
  - Note: the reading would have to run on the raw scan, before dewarping, and
    its coordinates be carried through the homography the dewarp computes. The
    row count itself transfers unchanged, and the model reads a raw 12MP photo's
    row count correctly at 55% linear, so the input is there.
  - Note: a two-panel sheet also doubles the strip count — 36 row strips plus a
    footer, against 29 for a single-panel sheet. Above 20 image blocks in one
    request a stricter per-image dimension limit applies to every image in it,
    documented as 2000px a side to be safe on all platforms. Unquantified rather
    than known-bad: a real run has already sent 29 strips 2262px wide through
    the CLI without complaint, so the first-party limit is evidently higher than
    the cross-platform figure. Worth measuring before a two-panel sheet is
    transcribed for real, since a rejected image fails the whole request and no
    board is read.
- [ ] Tell two sessions of one day apart when matching a traveller.
      {#same-day-sessions}
  - Rationale: `match_travellers` keys on the date alone, so two sheets scanned
    together — an afternoon and an evening session — leave every traveller for
    that day reporting `ambiguous_session_match` and matching neither. This did
    not arise while only a container's first page was digitized, because the
    second session was never stored.
  - Open question: the event text is the obvious tiebreak, and `session_keys`
    explains why matching on it was rejected — the sources spell one event four
    different ways. A fuzzy tiebreak used only when the date is ambiguous is a
    weaker claim than keying on it, and may be enough.
  - Note: this bites every multi-sheet feed, not an unusual one. A scanner feed
    is by nature a set of sheets from one day, so each of them lands in the
    ambiguous branch and no traveller matches any of them — the auto-reconcile
    join does nothing for exactly the containers the multi-page change
    introduces.
- [ ] Tell a table misread as two abutting panels from a genuine two-panel form.
  - Rationale: `resolve_sheet_geometry` refuses panels that overlap, but two
    panels reported flush against each other pass — and a single table read as
    two halves then resolves both against the same printed rules, cutting every
    board in two and transcribing it twice. Verified: panels at `[26,600]` and
    `[600,1174]`, each claiming 28 rows, yield 56 row boxes over 29 rules.
    Nothing notices, because the strips double alongside the boards.
  - Open question: the signal is whether the printed rules run continuously
    across the boundary — a genuine form leaves a gutter, a misread one does not
    — which is real new machinery rather than a threshold. Unlikely enough to
    defer: the right-hand half of a single table carries no board numbers, so a
    reading has little reason to call it a panel.

- [ ] Choose the scanner app and transport.
  - Open question: Android scanner + Drive-mirror vs. Syncthing — see spec.md
    (Open questions) and the Ingest section's tradeoffs.
  - Note: this gates where `inbox/` lives, not the pipeline code below it — the
    spine is built and tested already.
  - Note: `scoresheets/inbox/` exists now and scans have been through it, so
    nothing gates a run. Everything below it (`archive/`, `failed/`,
    `sessions/pending/`) is created on demand.
  - Note: the scanner app is settled in practice if not in principle — both real
    scans were written by Google's ML Kit document scanner, whose rectifying and
    cropping is what closed the resolution gap that per-row strips were
    introduced to work around.
- [ ] Write `configuration.toml` in the private tree.
  - Worktree: configuration-toml
  - Note: this is what a first real run waits on. The spine has been exercised
    end to end, but only against copies in a scratch tree — both scans are still
    sitting in the private tree's inbox, and nothing has been archived or
    written to `sessions/pending/`.
  - Note: it does not exist, and `python -m session_analysis.unreviewed.ingest`
    exits on its absence before reading the inbox — deliberately, since a run
    that transcribed a sheet and then stopped for want of a name would have
    spent the expensive part to do half the job. It wants `player_name`,
    `acbl_player_number` and `club_index_url`, all of which identify a real
    person, so it is the one piece of setup that has to be written by hand.
- [ ] Canonicalize the event slug through an alias table. {#canonical-slug}
  - Rationale: the slug is the footer text normalized literally, so `PABC morn.`
    one week and `PABC Morning` the next give two slugs for one game. Keys stay
    correct — each names its own session — but they read inconsistently across
    weeks.
  - Note: the alias table belongs in `unreviewed.configuration`, alongside the
    settings travellers.md's Configuration section calls for — auto-reconcile
    built that module for the player name, so this adds a table rather than a
    file.
  - Note: an unknown footer should fall back to the literal normalization it
    does today, not fail — a game played once should not need a config edit.

---

## Review UI {#review-ui}

**Goal:** a minimal, standalone tool to correct flagged fields, image beside
parsed value.

- [ ] Choose the tech (FastAPI + htmx, or Gradio).
  - Worktree: review-ui
  - Open question: framework, keybindings, commit semantics — see spec.md
    `#open-questions`.
- [ ] Tell a hand-corrected field from a traveller-sourced one before shipping
      any hand-editing of the reconciled fields. {#corrections-survive-rerun}
  - Worktree: review-ui
  - Rationale: reconciliation owns `deal`, `matchpoints`, `our_pair`, and
    `opponents`, and a re-run rewrites all four — clearing them outright when it
    runs with no traveller, which is what makes a withdrawn capture take its
    enrichment with it. Nothing in the model separates a value a person typed
    from one a traveller supplied, so today a re-run would silently delete a
    correction. Reconciliation is safe on its own, since it is the only writer;
    the hazard arrives with the second writer, which is this UI.
  - Note: whichever way it is solved — a provenance marker per field, a
    corrections overlay applied after the join, or reconciliation declining to
    clear what it did not write — it has to land before hand-editing does, not
    after.
- [ ] Rewrite a pending record where it was read from, before review starts
      renaming records. {#rewrite-where-read}
  - Worktree: review-ui
  - Rationale: `reconcile_pending_sessions` derives its destination from the
    record's contents, as `pending/{stem}.json`, while `read_pending_sessions`
    collects records with `rglob` from anywhere beneath `pending/`. The two
    agree only while every record sits flat under that directory and is named
    for its own key. A record review has renamed is therefore not updated but
    copied: the join writes a second file at the derived name, and one session
    then has two records, which double-count in matching and in
    `_stored_record_stems`.
  - Note: latent today — ingest is the only writer and writes flat, so nothing
    reaches the second path. It goes live with the first rename, and
    `session_keys.record_stem` says review renames the record either way, so
    this belongs before that lands.
  - Note: the fix is to carry each record's own path out of
    `session_matching._read_records` and write back to it, which changes what
    `read_pending_sessions` and `read_stored_travellers` return.
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

## Reporting

**Goal:** turn a digitized session into something a person reads — the boards as
text, and how the table's result compares with what the deal allowed.

- [ ] Render a session as plain text: every board's auction, opening lead,
      contract and result. {#session-transcript}
  - Worktree: session-transcript
  - Rationale: the pipeline's output today is a JSON record, and nothing renders
    it. So the first thing anyone wants from a digitized sheet — reading the
    session back — currently takes a JSON viewer.
  - Note: the model already carries all of this. `Board.number` fixes the dealer
    and vulnerability, `Board.auction` holds each written token with its circled
    and alerted marks, and `Board.outcome` resolves to a contract and result or
    to a passout. `AuctionEntry.raw` is populated whether or not the token
    parsed, so a board still renders where the parse fell short.
  - Note: what a run could not read belongs in the output rather than omitted
    from it. `Issue`s sit on the board and on its envelopes, and a transcript
    that silently drops an unreadable call reads as though the sheet said
    nothing there.
- [ ] Report each board's result against the double dummy for the best opening
      lead. {#result-versus-double-dummy}
  - Worktree: session-transcript
  - Rationale: a published double-dummy table already answers this. It states
    the tricks available with best play on both sides, which presumes the best
    lead — so this is a comparison to make, not an analysis to run.
  - Note: `TravellerBoard.double_dummy_tricks` carries the table, but `Board`
    does not — reconciliation fills `deal`, `matchpoints`, `our_pair` and
    `opponents` and stops there. Reading the stored traveller alongside the
    session, through the `CaptureReference` on `Source`, avoids widening the
    model for what is a reporting concern.
  - Note: only a pairs game publishes a traveller, so a teams session has
    neither deal nor table and this comparison has nothing to say for it. Say so
    rather than printing a result against nothing.
- [ ] Report each board's result against the double dummy for the lead actually
      made. {#result-versus-actual-lead}
  - Rationale: the published table cannot answer this one. It states what was
    available from the start, not what remained after a particular card, so this
    has to be solved rather than read.
  - Note: nothing in this project solves a deal — `double_dummy` appears here
    only inside the parsers that read a published table. This wants a solver as
    a new dependency, which is a decision worth taking on its own.
    `practice/squeezes` records the groundwork: `endplay` has no Python 3.14
    wheels but builds from sdist, verified 2026-08-04.
  - Note: sequence this after #session-transcript rather than beside it. Both
    write the same report, so run together they would settle its shape twice.

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
- [ ] Recover full names from a one-winner club recap. No longer blocked — the
      capture that answers it is already on hand. {#one-winner-recap}
  - Note: `club_html_parsing` reads the standings recap only after a heading
    naming a direction (`Section A North-South`). A one-winner movement ranks
    its pairs as a single list, so its recap heads the standings with the
    section alone — and that parser then collects no standings at all, leaving
    every pair with the surnames its board row prints.
  - Note: `club/R260629M.html` carries both forms and so is the fixture this
    needs. Its section A is one-winner and heads the standings
    `Scores after 8 rounds  Average: 48.0      Section  A`; its section B is a
    two-winner Mitchell heading `Section  B  North-South` and
    `Section  B  East-West`. The direction is simply absent — the layout is
    otherwise identical — and section A's pairs are exactly the ones that come
    out surname-only today.
  - Note: reconciliation matches our row on the surname alone as well as the
    full name, so this costs full names for the pairs in a one-winner section
    rather than the join itself (travellers.md #finding-our-row).
- [ ] Judge whether an unfilled field plus a prose issue is enough when two
      sources disagree. Trigger: enough reconciled sessions that disagreements
      have actually happened. {#disagreement-in-practice}
  - Rationale: travellers.md asked for the field to carry both candidates, and
    `Board` has nowhere to hold two values, so a disagreement currently leaves
    the field empty and names both accounts in the issue message. That preserves
    everything a person needs but nothing a program can act on — a review UI
    cannot offer "take the ACBL value" without parsing English.
  - Note: no capture on hand exercises this. Both 6/29 captures agree on every
    field of every board, so the path has only ever run against fixtures; how
    often real sources disagree is itself part of what this answers.
  - Note: the fix, if one is wanted, is an envelope per enriched field — the
    shape the sheet models already use for transcription. Worth doing when
    something consumes the candidates, not before.
- [ ] Judge whether swap detection earns its keep, and whether transpositions
      are the right search. Trigger: several digitized sheets reconciled.
      {#swap-detection-in-practice}
  - Rationale: it searches transpositions of every row pair, which catches the
    swap the 6/29 sheet carried but not a rotation — a skipped row sliding
    everything after it up by one. The argument for stopping there is that a
    rotation misaligns every later board and so announces itself through the
    cross-checks, where a two-row swap disturbs exactly two. Whether that holds
    is a question for real sheets.
  - Note: what to watch is false suggestions rather than missed ones. A
    suggestion a person has to think about and reject costs more than a swap the
    cross-checks would have surfaced anyway.
- [ ] Strip the masterpoint award a club recap prefixes to some player names.
  - Note: `club/gameresults2/tgif/R260717M.htm` parses pairs named names of the
    form `0.32(SB) First Last`, so the standings recap's award column is being
    read into the name beside it. Every pair in that capture is affected; the
    other club captures are clean, so it is that recap's layout rather than the
    parser's whole approach.
  - Note: it would defeat our-row matching for a session we played at that club,
    since the configured name would no longer match the printed one.
- [ ] Read the ACBL player number and the club index URL from the configuration
      rather than from a flag and a constant.
  - Note: the home exists — `unreviewed.configuration`, built where
    auto-reconcile needed the player name from somewhere. It already states all
    three settings travellers.md #configuration names, and the ingest command
    reads the name from it. What is left is the two callers still carrying their
    own: `fetch_travellers`'s required `--player-number`, and `club_fetching`'s
    `_CLUB_BASE_URL` and `_CALENDAR_PATH`.
  - Note: the flag should survive as an override rather than being replaced —
    fetching another player's results is a thing worth being able to do without
    editing a file.
- [ ] Remote-backed, size-tolerant durable store beyond `bridge-private`, if the
      growing game database outgrows the repo.
- [ ] Paper hand records as a traveller source, for sessions with no digital
      traveller — they carry the deal, too.
- [ ] Pianola as a traveller source, for club games that post only there
      (deferred: the sessions currently played don't use it).
- [ ] Transcribe the vendor two-column forms, not only resolve their geometry.
      {#two-column-forms}
  - Rationale: `sheet_geometry` reads both vendor samples correctly — 18+18 rows
    on Bridge Buddy and 16+20 on Baron Barclay, 36 row boxes each in board
    order. Everything after the cut is untried. Both samples are blank, so no
    two-panel sheet has been transcribed, and these forms carry no auction or
    notes columns, which the extraction prompt, the output schema and the parser
    contract all assume. Supporting a format is a form-template decision, not
    only cropping.
  - Note: which layout a session used follows from which sheet was to hand — the
    custom single-column form, or a double-column one provided at the venue —
    and not from the kind of event. Club games and tournaments both turn up
    either way, so this is a live driver rather than a sample-only concern. See
    spec.md `#scope`.
  - Note: the samples are in
    `bridge-private/session_analysis/scoresheets/samples`. Getting Baron Barclay
    as far as the cut needs #dewarp-needs-the-reading first: its panels differ
    in height, so the dewarp's own row-count vote refuses the sheet before the
    model is ever called.
- [ ] Maybe: grid-extent cross-check in `transcribe_sheet` — compare the
      detected `grid_left`/`grid_right` against where the dewarp placed the
      borders by construction (`_DEWARP_SIDE_MARGIN_IN_PITCHES` from the frame
      edges); deviation beyond ~1 pitch raises rather than cutting strips.
  - Rationale: catches asymmetric border failures — a border only partly visible
    resolves in the dewarp's median-filtered bands but dilutes out of
    detection's single full-height column profile, which today silently crops
    the `Bd` column and makes the model substitute `Vs` numbers (observed live).
    Also catches future drift between the two derivations.
  - Note: reshaped by the layout reading, and worth rethinking against it before
    it is written. `_panel_sides` no longer profiles the full height for the
    outermost line; it takes the printed line nearest the reported border, so
    the failure this was written against — detection diluting a partly visible
    border that the dewarp still resolved — is not the one to guard now. What
    remains worth catching is both readings agreeing on a border that is not the
    table's.
- [ ] Board-number continuity check in validation — flag a session whose
      transcribed board numbers don't run consecutively from their start.
      {#board-number-continuity}
  - Note: promoted from "maybe". `rules_bounding_rows` documents a hole only
    this can close: a reported grid box shifted bodily by more than half a row
    pitch resolves to the neighbouring run of rules, and the two cases are
    provably indistinguishable from the box alone — at 0.3 and 0.7 of a pitch
    the chosen run sits the same distance from the reported bounds and wins by
    the same margin. Swept on the v4 fixture, drift past about three quarters of
    a pitch resolves one row off with nothing raised: the first strip is the
    printed header row, the last board row is dropped, and the board count still
    matches the strip count so `_counted` stays quiet. Board numbers that stop
    running consecutively are what remains to notice it.
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
- [ ] A command that re-parses every capture on hand. Trigger: the next parser
      change.
  - Rationale: [travellers.md](travellers.md#testing) describes the check a
    parser change needs — parse everything before and after, and diff the
    records — which takes `store_travellers(refresh=True)` and so takes Python
    written by hand today.
  - Note: `fetch_travellers` is the wrong home for it. Its date argument means a
    run always fetches, where a re-parse wants no fetch at all.
- [ ] Revisit the open questions in
      [models.md](models.md#open-questions-and-todos) as their triggering work
      lands — each is a design decision deferred to the phase that resolves it.
      Resolve or re-defer each rather than letting the section rot.

---

## Cleanup

**Goal:** tidy-ups that only make sense once the work they trail has landed.

- [ ] Look for a shared shape between the two commands. {#shared-command-shape}
  - Rationale: `unreviewed.fetch_travellers` and `ingest` are both
    `python -m session_analysis.<module>` entry points that find the private
    tree, do a pass over it, and print what happened. Two is the first point at
    which a common shape is visible at all.
  - Note: look before extracting. They differ in more than they share — one
    takes arguments and the other none, one reports per source and the other per
    scan — so the answer may well be that they have only the tree lookup in
    common, which is already `private_paths`.
- [ ] Investigate whether `models` should stop importing the image pipeline.
      {#models-import-direction}
  - Rationale: `SheetFrame` holds a `SheetGeometry` and a `Quad`, which live in
    the modules that compute them — so `models` imports `sheet_geometry` and
    `sheet_dewarp`, and every consumer of the canonical models now loads Pillow
    transitively. `parsing`, `validation`, `travellers`, and all four capture
    parsers pay that cost for types they never touch.
  - Note: it is import weight, not a cycle — neither of those modules imports
    `models` — so nothing is broken. The question is whether the coupling is
    worth removing, not whether it is wrong.
  - Note: the obvious fix inverts it — move `Box`, `Point`, `Quad`, and
    `SheetGeometry` into `models` as canonical types, the way `Card` and `Deal`
    are shared with `travellers`, and have the image pipeline import them from
    there. That is a real refactor: `SheetGeometry` carries a `row_pitch` method
    and `Box` a `width` one, and `sheet_structure` reads `Box` from
    `sheet_geometry` too.
  - Note: measure before deciding. If Pillow's import cost is negligible for a
    command that loads it anyway, the tidier dependency graph may not earn the
    churn. models.md `#sheet-frame` records the reasoning as it stands.

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

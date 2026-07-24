# Travellers — capture, storage, and reconciliation

The traveller subsystem: acquiring the official game records for a session,
parsing them into a durable database, and joining them to a digitized sheet.
This is the detail behind the "Reconciliation" and "Traveller captures and PII"
sections of [spec.md](spec.md); the pipeline context and the sheet-side data
model live there and in [models.md](models.md) and are not repeated here.

## Concept: two datasets, joined

A traveller is not merely something consulted to check a board — it is a
first-class captured artifact. The design splits into two datasets that meet at
reconciliation:

- **Travellers are the game database.** One complete record per source per
  session: the session metadata, and for each board the deal, the double-dummy
  par, and _every table's_ result — both pairs by name and number, the contract,
  declarer, result, score, and matchpoints. This is a searchable record of past
  games, valuable on its own: it stands even for a session where no sheet was
  kept, and it is the only available record for tournaments.
- **Sheets are our annotations.** The auction, opening lead, freetext notes, and
  review flags for the boards we played — the fields nothing but the sheet
  records (see [spec.md](spec.md#source-of-truth-model)).
- **Reconciliation is the join.** Match the sheet's boards to the traveller,
  find our row, cross-check the recoverable fields, and copy the reconciled
  subset onto our record.

## What a traveller provides

Beyond the recoverable fields the traveller already owned as source of truth
(contract, declarer, result, matchpoints, opponent pair — see
[spec.md](spec.md#source-of-truth-model)), full capture adds:

- **The deal** — the four hands, board-level. The traveller (or a paper hand
  record) is its _sole_ source; the sheet says nothing about it. The canonical
  `Deal`/`Hand` types live in [models.md](models.md#deal).
- **The double-dummy par** — the makeable-tricks table and par contract,
  board-level, carried by both sources. This is analysis-stage data, captured
  here because it rides free in the captures and gives the eventual double-dummy
  comparison a reference to check our own solver against — a partial reference,
  for the reason given under [Double-dummy par](#double-dummy-par).
- **Every table's row**, not just ours — the whole traveller, which is what
  makes the capture a game database rather than a per-board lookup.

The ACBL capture carries an `opening_lead` field, but this club leaves it empty
for every row, so in practice the opening lead stays sheet-only (see
[spec.md](spec.md#source-of-truth-model)).

## Sources

Two sources cover a typical club session; tournaments have only ACBL Live.

- **ACBL Live** — the official ACBL record. Two surfaces, both keyed by the
  player number (`2475316`): club games at `my.acbl.org/club-results/...` and
  tournaments at `live.acbl.org/player-results/...`. Identifies pairs by name
  _and_ number, and carries the deal and par.
- **Club site** (`paloaltobridge.org`) — captures published by BridgeComposer.
  Identifies pairs by name, and carries the deal and par. Secondary
  corroboration.
- **Pianola** — some club games post only here. Deferred: the sessions currently
  played do not use it.

When both sources exist for a session, **merge them and flag disagreements**:
where they agree, the value is trusted; where ACBL and club disagree on a
recoverable field, that is surfaced for review as its own signal rather than
silently resolved. The two raw records are stored separately; the merge is a
reconciliation-time comparison, not a destructive combine.

## Acquisition

The goal is automatic fetching, with **manual save as the fallback** for
anything the fetch can't reach. Each source has a distinct fetch problem, so
they are separate investigations.

- **Club — discover, don't derive.** Different directors upload to different
  directories, so a date-derived URL is unreliable. The robust path is to scrape
  the index at `paloaltobridge.org/game-results/` and follow the link for the
  session's date and event.
- **ACBL — the fetch mechanism is an open investigation.** Both ACBL surfaces
  sit behind Cloudflare and (likely) authentication, so a plain HTTP request
  won't reach them. Candidate approaches — a headless browser with exported
  cookies, an authenticated session, or driving a real browser — each have
  tradeoffs. Driving the user's own Chrome (e.g. the `claude-in-chrome` skill)
  is attractive because it inherits the logged-in, past-Cloudflare session, but
  Claude runs as a separate OS user from the browser, so its viability is
  unconfirmed. Resolving this is part of the fetch task, not settled here.

Whichever fetch is used:

- **Match by parsed metadata, never the filename or URL.** Each capture carries
  its event name and date; parse those, derive the session key, and match to
  sessions — mirroring the sheet's own footer self-naming. Filenames
  (`1472071.html`, `R260629M.html`) and URL patterns are opaque or inconsistent.
- **Reconciliation auto-runs on availability.** A fetched traveller that matches
  a pending session triggers reconciliation automatically; there is no separate
  "reconcile" command. The escape hatch — finalizing a session that no traveller
  ever arrives for — is the one explicit action (see
  [Reconciliation](#reconciliation)).

## Traveller data model

Structured JSON, one record per source per session. This is the game database's
storage shape; it replaces the `Source.travellers` placeholder
(`tuple[str, ...]`) in [models.md](models.md).

- **`Traveller`** — `source` (ACBL / club), the source reference (URL or game
  id), event, date, section(s), and the boards.
- **`TravellerBoard`** — the board number; the `Deal`; the double-dummy par; and
  the rows. The deal and par are board-level (shared across tables); the results
  are per-row.
- **`TravellerResult`** — one table's play of the board: the North-South and
  East-West `PairIdentity`, the contract, declarer, penalty, result, the
  North-South and East-West scores and matchpoints, and the opening lead when
  the source records one. The sheet records none of the pair, contract, result,
  or deal fields; they come entirely from the traveller.

The shared `Deal`, `Hand`, `Card`, `Direction`, and `PairIdentity` types are
canonical-model types defined in [models.md](models.md); the traveller types
reuse them.

### Double-dummy par

Each source condenses the same underlying facts its own way — ACBL writes a row
per side with a slash where the two seats differ (`E/W: 2♣ 5/6♦ 6♥ 7♠ 6NT`), the
club a semicolon list that collapses to the side when the seats agree
(`W 6♦; E 5♦; EW 2♣;`). Both **normalize to one canonical shape on parse**, so
the sources become directly comparable and a disagreement between them surfaces
like any other.

- **Makeable tricks** — one cell per `Direction` and `Strain`, twenty in all,
  holding the trick count rather than the contract level the sources print. A
  cell is null where the source prints a level of zero: that means fewer than
  seven tricks without saying how many, so null is the honest value and a zero
  trick count would be a fabrication. This is what makes the captured table a
  _partial_ reference for checking our own solver — it pins the values at seven
  tricks and above, and merely bounds the rest.
- **`Par`** — the par score and the par contracts achieving it. The score is
  always from North-South's perspective, and sits above the contracts because
  one score is shared by all of them.
- **Par contracts reuse `Resolution`** — the same `PlayedContract | Passout`
  union a played board resolves to (see [models.md](models.md#outcome)). Par is
  the contract optimal bidding would reach and play, so pairing a `Contract`
  with its `Result` is exactly the right shape, and a deal where nothing makes
  pars at a passout. That case is absent from the captures on hand but costs
  nothing to support, since the union already models it.
- **A side-level par expands to one contract per seat.** Both sources mix the
  two forms — `6S-EW` alongside `6H-E` — and `Contract.declarer` is a single
  seat. A side means _both_ of its seats achieve the score, so expanding it
  loses nothing; it is merely verbose, since `4S-EW+1/4H-EW+1` becomes four
  contracts, one per seat per strain.

A par result is recoverable even where a source omits it, since a contract's
trick count is its declarer's makeable tricks in that strain — for a sacrifice
as much as for a making contract. ACBL writes no marker at all when the par
contract makes exactly, showing only `+N` or `-N`; the club states the result on
every par seen, `=` included, so where both sources cover a board the club's
result checks the reconstruction.

## Reconciliation

Reconciliation joins a digitized sheet to its traveller(s) and enriches the
sheet's record. It is best-effort: every traveller cross-check degrades to
skipped rather than failing (see [Graceful degradation](#graceful-degradation)).

### Finding our row

The sheet never records who we are, and partners vary week to week — so our pair
cannot be a fixed identity. **Match on the user's own name alone:** on each
board, our row is the one whose North-South or East-West pair contains the
configured name, in either direction, with any partner. Name match is
authoritative; when the name is found in no row (a wrong-session traveller, a
misspelling), the board is flagged for review rather than guessed at.

This dissolves the harder "recover our identity by content" problem: we know who
we are, so reconciliation recovers only the _opponents'_ identity (the other
pair in our row) and the matchpoints.

### Cross-checks and enrichment

- **Recoverable fields** (contract, declarer, result, matchpoints) are compared
  between our row and the sheet. A disagreement raises the board's review
  priority. For the **declarer**, neither side is authoritative — travellers are
  sometimes wrong where the local notes are right — so a mismatch is surfaced,
  never auto-resolved (see [spec.md](spec.md#reconciliation)).
- **Enrichment**: the reconciled subset — deal, matchpoints, and both pair
  identities — is copied onto our `Board`, so the per-session record stays
  self-contained for the analysis stage; the par stays in the traveller record,
  read from there by the analysis stage. When two sources disagree on a copied
  field, the field is flagged and carries both candidates rather than taking a
  silent tiebreak.
- **The deal enables a new integrity check.** The opening lead (sheet-only) must
  be a card in the hand of declarer's left-hand opponent. A violation flags the
  lead, the declarer, or the board numbering — a check the sheet alone cannot
  do, and a third independent signal for the swap detection below.

### Swap detection

Row-order errors are the expected failure mode (the user swapped boards 20 and
21 on the 6/29 sample). Detect them with a **best-alignment permutation** of
sheet rows against traveller boards: if sheet row N matches traveller board M
and vice versa, surface a "likely swap." **Suggest, never auto-apply** — two
boards with identical results are indistinguishable, so a human confirms. The
deal-versus-lead check and the computed dealer/vulnerability are additional,
traveller-content-independent swap signals.

### Timing and the escape hatch

Travellers are published after the session — sometimes days later, sometimes
never (paper-only hand records; a club game that posts only to Pianola). So
reconciliation is decoupled from ingest and **review is deferred until it
runs**: the sheet-only fields are captured at ingest, but the record is not
reviewed until the traveller has enriched it, because the deal it supplies is
what the whole downstream analysis rests on.

The **escape hatch** finalizes a session no traveller ever arrives for: an
explicit action produces a reviewable record from the sheet plus computed
dealer/vulnerability alone. That record is legitimate but analytically
incomplete — no deal, no matchpoints, no opponent identities.

### Graceful degradation

With no traveller, every cross-check is skipped rather than failing, and the
sheet stands alone. The pipeline runs to completion with zero travellers; the
consequence is simply an un-enriched record, surfaced through the escape hatch.

## Configuration

Reconciliation and acquisition need a small amount of stable, user-specific
configuration, kept out of the code:

- **The user's name**, as it appears in traveller pairs, for our-row matching.
  Name variants (nicknames, initial-plus-surname) may need more than one form or
  a normalization step — an open question until real captures show the range.
- **The ACBL player number** (`2475316`) for the fetch surfaces.
- **The club index URL** (`paloaltobridge.org/game-results/`).

## Storage and PII

A full game database is every club member's names and results accumulated over
time — more sensitive than a single session's capture, and never suitable for
the public repo.

- **Location**: raw captures and parsed JSON both live in the `bridge-private`
  repo and/or a remotely-backed service, never the public repo. Near-term, the
  existing `session_analysis/travellers/` directory moves out of the public repo
  into `bridge-private` (alongside `scoresheets/`), read through a configurable
  path.
- **Size-consciousness**: the parsed JSON is the durable artifact and stays
  small; raw HTML is kept lean — the ACBL "save page complete" bundle drags in
  an `_files` directory of scripts and images (~3.4 MB, several times the HTML
  itself) that is dropped, keeping only the HTML needed to re-parse or debug.
- **Store format**: structured JSON now, script-searchable as-is. A queryable
  store (most likely SQLite) stays in the backlog, to be settled when the
  analysis UI is designed (see [spec.md](spec.md#open-questions)).

## Testing

- **HTML parsers** — committed fixtures with placeholder member names exercise
  the parse logic in the public repo; the real captures, kept in
  `bridge-private`, back integration checks. This mirrors the extraction
  fixtures' placeholder convention (see [spec.md](spec.md#testing-strategy)).
- **Name match, source merge, and the deal-versus-lead check** — pure logic,
  unit-tested with hand-constructed travellers and boards, with zero fetching.
- **Swap detection** — a fixture with the known 6/29 board-20/21 swap asserts
  the swap is _suggested_; identical-result boards assert no false auto-apply.

## Open questions

- **ACBL fetch past Cloudflare** — the mechanism (headless browser plus cookies,
  driving a real browser despite the separate-user boundary, or another
  approach), resolved as part of the fetch task.
- **Club index-scrape robustness** — handling the varying director directories
  and distinguishing morning/afternoon sessions from the index.
- **Name-variant handling** — how many forms of the user's name appear across
  captures, and whether a normalization step is needed.
- **Remote-backup service** — whether `bridge-private` alone suffices or a
  separate size-tolerant backing service is warranted.
- **Pianola** — support for club games that post only there, deferred until a
  played session needs it.

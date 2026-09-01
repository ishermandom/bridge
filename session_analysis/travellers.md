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
  kept, and it is the only source of the deal, which no sheet records. For
  tournaments it is the only _traveller_ source — there is no club-site copy to
  corroborate it — though a sheet is kept for those too.
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

The ACBL capture carries an `opening_lead` field, but the Palo Alto club leaves
it empty for every row, so in practice the opening lead stays sheet-only (see
[spec.md](spec.md#source-of-truth-model)).

## Sources

Two sources cover a typical club session; tournaments have only ACBL Live.

- **ACBL Live** — the official ACBL record. Two surfaces, both keyed by the
  player number: club games at `my.acbl.org/club-results/...` and tournaments at
  `live.acbl.org/player-results/...`. Identifies pairs by name _and_ number, and
  carries the deal and par. The two are separate parses despite the shared
  publisher: a club page carries a JSON blob and is read from that blob, while a
  tournament page carries none and is read from the markup, which arrives
  already built in the server's response.
  - Only a **pairs** game publishes a traveller. A team game's page carries
    match scores and no per-board rows at all, so there is nothing in it to
    parse — reported as such rather than passed off as an empty traveller.
- **Club site** (`paloaltobridge.org`) — each game published by BridgeComposer,
  as a PBN and as HTML. Carries the deal and par. Names a row by its pair of
  surnames (`Alfa-Bravo`); full names appear only in the standings recap that
  both formats embed, reachable from a row by its section and pair number.
  Secondary corroboration.
- **Pianola** — some club games post only here. Deferred: the sessions currently
  played do not use it.

When both sources exist for a session, **merge them and flag disagreements**:
where they agree, the value is trusted; where ACBL and club disagree on a
recoverable field, that is surfaced for review as its own signal rather than
silently resolved. The two raw records are stored separately; the merge is a
reconciliation-time comparison, not a destructive combine.

### Which club format to parse {#club-format}

The PBN is much the easier target — a documented, tagged format whose board
records hold the deal, the double-dummy table, and par, and whose `ScoreTable`
section holds every row. But it is a supplement rather than a substitute, for
two reasons:

- Roughly a sixth of games have no PBN at all, and the gap is concentrated in
  the two directors who publish their HTML under a `C` prefix rather than an `R`
  one; HTML is present for all but a handful of games.
- **Most PBNs that do exist carry no traveller.** Several directors upload a
  hand record — deals, double dummy, and par, with no `ScoreTable` at all. Of
  the captures on hand, only one of five has the rows. So for most games the PBN
  supplies the deal and the analysis while the HTML supplies the rows.

The HTML parser therefore has to exist regardless, and the PBN parser is worth
having anyway: it is far more robust than markup scraping for the fields it does
carry, and its `ScoreTable` gives a second independent reading of the rows
wherever both files exist. Across the one game published both ways, the two
parsers agree on every deal, par, contract, result, score, and matchpoint.

The two HTML variants differ only in presentation. Their per-board score tables
are identical; `R` additionally carries the par contract, where `C` carries the
par score alone, and the double-dummy opening-lead notes. A parser should key on
the score table's own class rather than on the board container, whose class
attribute `C` omits.

A capture saved from a browser also differs from the same file fetched directly
— attribute quoting, entity decoding, and inserted `<tbody>` elements are the
browser's doing. Reading through a real HTML parser absorbs the difference;
matching against raw markup would not.

## Acquisition {#acquisition}

The goal is automatic fetching, with **manual save as the fallback** for
anything the fetch can't reach. Each source has a distinct fetch problem, so
they are separate investigations. One command, the `fetch_travellers` module,
runs all of them for a date, and the parse pass that turns what landed into
records.

- **Club — discover, don't derive.** Different directors upload to different
  directories, so a date-derived URL is unreliable. Fetching instead reads the
  calendar at `paloaltobridge.org/game-results/`, which renders a month per page
  and gives each day a cell listing that day's games with links to whatever
  files each one has; which files exist is read from those links rather than
  derived from the date. Plain HTTP suffices — no authentication, and
  `robots.txt` permits the results paths. Implemented as `fetch_travellers` in
  `club_fetching.py`, which downloads each game's PBN and HTML under the site's
  own relative path, because two directors regularly publish the same filename
  for games on one date.
- **ACBL tournaments — a headless browser past Cloudflare.** Every ACBL page
  sits behind a Cloudflare "managed challenge" — JavaScript a browser must run
  before the real content loads — so a plain HTTP request is turned away. A
  headless Playwright browser clears it with no login or cookies: the full
  Chromium (not the lighter headless shell) given a real viewport and locale
  runs the challenge and is let through. Tournament results are public and
  enumerable by player number at `live.acbl.org/player-results/<number>`, a
  table listing each session with a link to its traveller. Implemented as
  `fetch_tournament_travellers` in `acbl_fetching.py`, which reads that index,
  keeps the sessions played on a date, and saves each session's rendered HTML —
  lean by construction, since driving the page ourselves skips the asset bundle
  a browser's "save page" drags in.
- **ACBL club games — the same fetch, one host over.** A player's club sessions
  are public too, listed by player number at
  `my.acbl.org/club-results/my-results/<number>` in the same shape as the
  tournament index — a dated table of game links — so the same headless-browser
  fetch and index walk apply, only against `my.acbl.org` and its
  `club-results/details/<id>` travellers. A club detail page embeds its
  traveller as a `var data = {...}` JSON blob, a cleaner parse than its HTML
  tables. Club games also have a BridgeComposer copy on the club site that
  `club_fetching` fetches, so the ACBL club record is corroboration rather than
  the sole one.

Whichever fetch is used:

- **File under the publishing site's directory.** Both fetchers save beneath the
  directory for the site they read, and a capture saved by hand goes in the same
  place; see [Storage and PII](#pii) for why that is what picks the parser.
- **Match by parsed metadata, never the filename or URL.** Filenames
  (`1472071.html`, `R260629M.html`) and URL patterns are opaque or inconsistent,
  so what a capture belongs to is read out of the capture itself. What that
  comes to in practice is [Matching a capture to its session](#matching).
- **Reconciliation auto-runs on availability.** A fetched traveller that matches
  a pending session triggers reconciliation automatically; there is no separate
  "reconcile" command. The escape hatch — finalizing a session that no traveller
  ever arrives for — is the one explicit action (see
  [Reconciliation](#reconciliation)).

### Matching a capture to its session {#matching}

The session key and the capture match are two jobs, not one. The key names a
session, derived from its sheet's own footer; the match decides which session a
capture belongs to. They were once meant to be the same mechanism — derive the
key from each side and compare — and the data does not allow it.

One session's event name, as each source spells it:

| source        | event                                     |
| ------------- | ----------------------------------------- |
| sheet footer  | handwritten freetext, transcribed as-is   |
| club PBN      | `Monday Pairs`                            |
| club HTML     | `Monday Pairs`                            |
| ACBL club     | `Monday Morning \| Palo Alto Bridge Club` |
| club calendar | `Palo Alto Duplicate`                     |
| the real club | `John & Will's Monday Bridge`             |

No normalization rule takes all of those to one slug, and any event comparison
between a capture and a sheet rejects true matches far more often than it
catches false ones. **So the match reads the date alone**, which every source
states and states alike; `unreviewed.session_matching` holds it.

Date alone is ambiguous only on a day two sessions were played. A capture
matching more than one is reported and matched to neither, rather than guessed
at — only the ACBL club surface publishes anything time-like today, as the
coarse `club_session` label (`Monday Morning`), and the club's own files carry a
date and nothing finer. tasks.md `#multi-session-days` carries the work to
resolve it.

## Traveller data model {#traveller-model}

Structured JSON, one record per source per session. This is the game database's
storage shape; it replaces the `Source.travellers` placeholder
(`tuple[str, ...]`) in [models.md](models.md).

Three types, defined in `travellers.py`, which is where each field's meaning
lives: a **`Traveller`** per source per session, holding **`TravellerBoard`**s,
each holding a **`TravellerResult`** per table that played it. The deal and the
double-dummy analysis sit on the board, shared by every table; the pairs,
contract, result, and scores sit on the row. The shared `Deal`, `Hand`, `Card`,
`Direction`, `Side`, and `PairIdentity` types are canonical-model types from
[models.md](models.md).

The design decisions behind that shape, which the types themselves cannot
explain:

- **`TravellerSource` names all four capture formats**, not the two publishers,
  because each is a distinct parse: club PBN, club HTML, ACBL club, ACBL
  tournament.
- **The score is one signed number from North-South's perspective**, not one per
  side. The sources spell it two ways — a value in one side's column and a blank
  in the other, or the same number written twice with opposite signs — and both
  collapse to the signed form without loss. Matchpoints stay per side: they are
  genuinely two numbers, and what they sum to varies by source (see
  [the top](#tournament-top)).
- **Dealer and vulnerability are stored nowhere**, because both follow from the
  board number (see [models.md](models.md#dealer-and-vulnerability)). What a
  source prints is read only to be checked against the computed value, which is
  how a board read off the wrong part of a capture surfaces.
- **A section is a property of a row, not of the capture.** Each `PairIdentity`
  carries the section its pair sat in, which is what tells pair 3 in section A
  from pair 3 in section B. There is deliberately no session-level list of
  sections: it would only restate what the rows already say. If a use appears —
  telling a half-saved capture from a whole one is the plausible one — it can be
  derived then, or added back with a caller that needs it.
- **Nothing a capture says is discarded for being unreadable.** A parser that
  cannot read a row keeps the rest and records an `Issue` on the row or board,
  so reconciliation surfaces it; the public parse entry points do not raise for
  anything a capture contains. See travellers.py.

### Reporting what could not be read {#issue-reporting}

Every parser ranks an issue by what the failure cost, on one ladder shared by
all four so the same trouble reads the same whichever source it came from:

- **High** — a structural loss: a capture that yielded no game, a board record
  nothing can place. The file or the parser's grasp of the format is wrong, and
  what else the capture says is in doubt.
- **Medium** — part of the record of play: a row that would not split, a
  contract that would not read, a deal.
- **Low** — analysis alone: par, or a cell of the double-dummy table. The play
  is still fully read; only the commentary on it is short.

Within a parser a helper may raise, where it sits below the level that knows
what its failure costs — but the raise is caught at the row or the board it came
from, never at the entry point, which would trade an exception for an empty
traveller and lose the same rows. `notation` and `acbl_notation` are the shared
translators and so always raise; their callers catch.

`issue_reporting` holds the `Failure` and `Read` types every parser needs to
work this way. Each parser declares its own table of `Failure` constants,
because what a source can fail at is particular to that source where the ladder
above is not.

### Double-dummy par

Each source condenses the same underlying facts its own way — ACBL writes a row
per side with a slash where the two seats differ (`E/W: 2♣ 5/6♦ 6♥ 7♠ 6NT`), the
club a semicolon list that collapses to the side when the seats agree
(`W 6♦; E 5♦; EW 2♣;`). Both **normalize to one canonical shape on parse**, so
the sources become directly comparable and a disagreement between them surfaces
like any other.

- **Makeable tricks** — one cell per `Direction` and `Strain`, twenty in all,
  holding the trick count rather than the contract level the sources print. A
  cell is null only where its source declined to say how many, so how complete
  the table is varies by source:
  - The **club's HTML** lists the contracts that make and nothing else, so every
    cell below seven tricks is unstated and therefore null. Its table pins the
    values at seven tricks and above and merely bounds the rest — a _partial_
    reference for checking our own solver.
  - The **club's PBN** states all twenty exactly, in its `OptimumResultTable`.
  - **ACBL** states all twenty too, switching notation below seven tricks: a
    number _before_ the strain is a makeable level, a number _after_ it is the
    trick count itself. The one genuinely-null case is ACBL's `1/-S`, where a
    dash stands in for the level of a seat that makes nothing — and even that is
    accompanied by a trick-count cell wherever it has been seen.
- **`Par`** — the par score and the par contracts achieving it. The score is
  always from North-South's perspective, and sits above the contracts because
  one score is shared by all of them.
- **Par contracts reuse `Resolution`** — the same `PlayedContract | Passout`
  union a played board resolves to (see [models.md](models.md#outcome)). Par is
  the contract optimal bidding would reach and play, so pairing a `Contract`
  with its `Result` is exactly the right shape, and a deal where nothing makes
  pars at a passout.

  No parser produces that `Passout` yet: no capture on hand shows a passed-out
  par, so how a source would spell one is unknown. Whether it can occur at all
  is open — the tempting argument that someone always makes at least 1NT does
  not hold, because double-dummy tricks depend on which seat declares, so the
  four notrump cells are not complementary. Across 196 boards stating all twenty
  cells, none has every cell below seven, but the lowest board maximum seen is
  exactly seven. The union stays; producing one is pending feature work, waiting
  on a live example.

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

### The trick count a tournament does not publish

ACBL's tournament pages print a score on every row but no trick count — the
results column is commented out of their markup. The canonical `Result` is
therefore **recovered by scoring**: score all fourteen possible results of the
contract and take the one matching the published score. For a fixed contract and
vulnerability every extra trick is worth strictly more than the last, so exactly
one can match and no inverse has to be written or maintained. The vulnerability
comes from the board number, as everywhere else.

Recovering a trick count this way is what `scoring.py` exists for, ahead of the
analysis stage that will want scoring anyway. The independent evidence is the
captures themselves: every row of both tournament sessions reconciles, so ACBL's
own scores agree with the scoring table throughout.

### The top a tournament scales its matchpoints to {#tournament-top}

A row's two sides' matchpoints sum to the board's top, and on ACBL's tournament
pages that top is one number for the whole session rather than one per board. A
board played fewer times than the rest is scaled up to it, which is what stops
its matchpoints from being halves: both captured sessions top at 15, and a board
played 14 times carries 0.07, 1.21, 8.64, and 14.93 among its values.

Worth knowing before reading an odd-looking matchpoint as a parse fault. The
constant total is also what makes a mis-joined row visible from outside, since
each row is printed once in either side's table and the two are joined on the
pair numbers they both name — though a director awarding an average to both
sides puts a row off the total legitimately.

## Reconciliation {#reconciliation}

Reconciliation joins a digitized sheet to its traveller(s) and enriches the
sheet's record. It is best-effort: every traveller cross-check degrades to
skipped rather than failing (see [Graceful degradation](#graceful-degradation)).

### Finding our row {#finding-our-row}

The sheet never records who we are, and partners vary week to week — so our pair
cannot be a fixed identity. **Match on the user's own name alone:** on each
board, our row is the one whose North-South or East-West pair contains the
configured name, in either direction, with any partner. Name match is
authoritative; when the name is found in no row (a wrong-session traveller, a
misspelling), the board is flagged for review rather than guessed at.

Matching on the configured name dissolves the harder "recover our identity by
content" problem: we know who we are, so reconciliation recovers only the
_opponents'_ identity (the other pair in our row) and the matchpoints.

**Two spellings match: the configured full name, and its surname alone.** Both
ACBL surfaces print full names, and so does a club recap whose standings could
be read; a club recap whose standings could not be read leaves the surnames its
board rows print (see tasks.md `#one-winner-recap`), and a club PBN prints
surnames or no names at all. Nothing else matches — testing a bare surname
against every printed full name would claim every namesake in the field, which
at a club is a real risk rather than a theoretical one. A board naming us twice
is reported rather than guessed at.

**The ACBL player number is deliberately not carried.** It would be an exact
key, but it exists only on the two ACBL surfaces — which already print full
names. The sources whose names are weak are the club's, and they do not publish
it at all. So carrying it would touch every parser and `PairIdentity` without
improving the case that actually needs help.

### Cross-checks and enrichment

- **Recoverable fields** (contract, declarer, result) are compared between our
  row and the sheet. A disagreement raises the board's review priority. For the
  **declarer**, neither side is authoritative — travellers are sometimes wrong
  where the local notes are right — so a mismatch is surfaced, never
  auto-resolved (see [spec.md](spec.md#reconciliation)). The matchpoints are not
  among the compared fields: the sheet has no matchpoint field at all, by
  design, because our own estimate of them is not worth storing (see
  [models.md](models.md#vision-output)) — so they are enrichment only.
- **Enrichment**: the reconciled subset — deal, matchpoints, and both pair
  identities — is copied onto our `Board`, so the per-session record stays
  self-contained for the analysis stage; the par stays in the traveller record,
  read from there by the analysis stage. When two sources disagree on a copied
  field, the field is left unfilled and an issue names what each source said,
  rather than taking a silent tiebreak — a record that asserts nothing is honest
  where one that picks a winner is not.
- **Detail is not disagreement.** Two sources routinely describe one thing at
  different depths: `Last & Person` and `First Last & Second Person` are one
  pair written twice. A pair merges when its seat — number, side, and section —
  matches outright and each name abbreviates the other, and the fuller spelling
  is kept. That is not the tiebreak above, because nothing is discarded: the
  sparser spelling is contained in the fuller one. The same holds across formats
  — a club PBN hand record supplies the deal for boards its HTML recap never
  covered, and a board dealt but never reached is a board nobody played rather
  than a source disagreeing.
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

### Timing and the escape hatch {#timing}

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

### Graceful degradation {#graceful-degradation}

With no traveller, every cross-check is skipped rather than failing, and the
sheet stands alone. The pipeline runs to completion with zero travellers; the
consequence is simply an un-enriched record, surfaced through the escape hatch.

## Configuration {#configuration}

Reconciliation and acquisition need a small amount of stable, user-specific
configuration, kept out of the code. Where the private data lives is not part of
it — that is found rather than configured, per [Storage and PII](#pii).

- **The user's name** in full, for our-row matching. One value covers every form
  the captures on hand print, because the surname is derived from it rather than
  configured beside it — see [Finding our row](#finding-our-row).
- **The ACBL player number**, which keys both fetch surfaces.
- **The club index URL** (`paloaltobridge.org/game-results/`).

## Storage and PII {#pii}

A full game database is every club member's names and results accumulated over
time — more sensitive than a single session's capture, and never suitable for
the public repo.

- **Location**: raw captures and parsed records both live in the
  `bridge-private` checkout beside this one, never in the public repo. That
  checkout gives each project a directory named for the public subproject it
  accompanies, so these sit under `session_analysis/` alongside the scoresheet
  images and the reconciled sessions. Everything hangs off that one root, which
  `private_paths` locates, so the trees cannot drift apart and there is a single
  thing to repoint at a different checkout.
- **Found, not configured**: the two repos are already kept as siblings, so
  looking beside this checkout asks nothing of the person running the code and
  leaves no setting to go stale. The one place a sibling walk misleads is a
  worktree, which has no `bridge-private` of its own next to it; asking git for
  the repository's common directory names the main checkout from inside a
  worktree and from the checkout itself alike.
- **Filed by publishing site**: a capture sits under a directory named for the
  site that published it, and that is what decides which parser reads it.
  Nothing inside a capture reliably announces its own format — the ACBL login
  page a gated game answers with parses as far as "no page data" rather than
  declining to be an ACBL page at all — so the judgment is made once, by whoever
  files the capture, rather than guessed at on every read. A hand-saved capture
  thereby gets the same standing as a fetched one, which is what the manual-save
  fallback needs.
- **Provenance**: a stored traveller names the capture it came from, and the URL
  that capture was fetched from where a fetch recorded one. The two answer
  different questions and neither replaces the other: the path always exists and
  always resolves to a file that can be parsed again, while the URL exists only
  for a fetched capture and is the half nothing can recover once it is gone. The
  fetchers record it as they save, into a sidecar named for the capture it sits
  beside, rather than leaving it to be reconstructed from a mirrored path —
  which reorganizing the tree would silently invalidate. A sidecar travels with
  the file it belongs to, so a later reorganization carries provenance along
  instead of having to rewrite a shared record to match, and two fetches saving
  into one directory never contend for the same file.
- **Size-consciousness**: raw HTML is kept lean — a browser's "save page
  complete" drags in an `_files` directory of scripts and images several times
  the size of the HTML itself, which is dropped, keeping only what is needed to
  re-parse or debug. The fetchers never produce one, since driving the page
  directly skips the bundle. The parsed records are not the small half of the
  store, though: they run roughly half the size of the captures they come from.
  Most of a record is its result rows, since every row names its pairs inline —
  the deal is about a fifth of a record and the double-dummy table a fiftieth —
  so the inline-pairs tradeoff the backlog already records is what a compact
  store would need to address, not the analysis riding along with each board.
- **Readable over small, for now**: records are written indented. Compact JSON
  would save around three fifths of the bytes, but the records live in a git
  repo and the check that a parser change altered nothing is a diff of them, so
  legibility is worth more than the space at this volume. Revisit when the
  durable store is designed rather than now.
- **Store format**: structured JSON now, script-searchable as-is. A queryable
  store (most likely SQLite) stays in the backlog, to be settled when the
  analysis UI is designed (see [spec.md](spec.md#open-questions)).

## Testing {#testing}

- **Capture parsers** — committed fixtures with placeholder member names
  exercise the parse logic in the public repo; the real captures, kept in
  `bridge-private`, back integration checks. This mirrors the extraction
  fixtures' placeholder convention (see [spec.md](spec.md#testing-strategy)).
  Each test file writes out the few fields or elements a test turns on, and
  keeps a small minority that parse a whole captured file end to end — one per
  distinct published shape, which is why the club HTML has two (its `R` and `C`
  variants) and the ACBL club has two (its one- and two-winner movements, which
  differ in whether a pair number names one pair or two). A test's builders take
  domain values and serialize themselves, so a test never spells out markup or
  JSON it is not about. Surnames come from the NATO alphabet in its own
  spellings — `Alfa`, `Juliett` — so a name reads as a placeholder on sight.
- **Fixture markup keeps the source's shape** — BridgeComposer emits one line
  per table row, so a club HTML fixture carries lines of several hundred columns
  and the real captures run past two thousand. Wrapping them for readability
  would make a fixture less like its input, and the standings recap is a `<pre>`
  block whose line breaks the parser splits on. A PBN's name columns are padded
  to the widths its `ScoreTable` header declares, so a placeholder there cannot
  change length without being repadded to match.
- **Which real capture is which** — worth knowing before reaching for "an ACBL
  club capture" to check something against. Only a pairs game carries a
  traveller: `1484015.html` is a team game, whose page has no per-board rows at
  all. Of the two pairs games, `1472071.html` ran a one-winner movement and
  `1441256.html` a two-winner one, so only the second names a direction on its
  pair summaries. `1441256.html` is also the only capture that does not parse
  clean: ACBL wrote board 18's par as `Par: 660 4NT-NT+1`, repeating the strain
  where the declarer belongs, which the parser reports and the board survives.
  `1430431.html` is not a game page at all — it is the ACBL login page the fetch
  came back with, kept as the example of what a gated game saves as. The two
  tournament captures are the two sessions of one event, 26 boards and a single
  section apiece, and both parse clean.
- **Showing a parser change alters nothing** — run `traveller_store` with
  `refresh` before and after and diff the records it writes, which is what
  `refresh` is for: an ordinary run skips a capture whose record already
  postdates it. The committed fixtures are too small to be the whole check; the
  captures under `bridge-private/session_analysis/travellers` are what exercise
  the shapes a publisher actually emits. For a rewritten regex, also run the old
  pattern against the new over generated inputs that include near-misses, since
  a capture only exercises what it happens to contain.
- **Name match, source merge, and the deal-versus-lead check** — pure logic,
  unit-tested with hand-constructed travellers and boards, with zero fetching.
- **Swap detection** — a fixture with the known 6/29 board-20/21 swap asserts
  the swap is _suggested_; identical-result boards assert no false auto-apply.

## Open questions

- **Name variants beyond the surname** — the captures on hand print the full
  name or the surname alone, both of which match. A nickname or an
  initial-plus-surname would not, and none has appeared yet; if one does, the
  configured name grows into a list of forms rather than changing shape.
- **Remote-backup service** — whether `bridge-private` alone suffices or a
  separate size-tolerant backing service is warranted.
- **Pianola** — support for club games that post only there, deferred until a
  played session needs it.

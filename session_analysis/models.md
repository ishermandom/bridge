# Models and validators

A deep dive on the data model for scoresheet digitization and the validation
that runs over it. This is the detail behind the "Data model" and "Validation"
sections of [spec.md](spec.md); the pipeline context, source-of-truth model, and
notation convention live there and are not repeated here.

The chain this document specifies, in order:

1. **VLM output** — the faithful, minimally-interpreted JSON the vision model
   returns.
2. **Parsing** — pure code that turns that output into the canonical model,
   logging an issue per thing it can't parse rather than failing.
3. **Canonical model** — the typed, stored shape, where every parsed value sits
   beside the raw text it came from.
4. **Validation** — a non-raising pass that flags suspect boards for review.

## Design principle: nothing is garbage

A handwritten sheet is _expected_ to contain errors — that is the entire reason
the review step exists. So no single misread ever aborts a parse. A bid
transcribed `IC` instead of `1C`, a contract the VLM couldn't segment, a glyph
that isn't a real strain — each is **captured verbatim, flagged, and left beside
its eleven healthy neighbors**. The board is stored as a best-effort parse ahead
of review; review corrects the flagged fields; the parse re-runs.

This principle drives two structural decisions throughout:

- **Each written token sits in a parse envelope.** A per-token wrapper (e.g.
  `AuctionEntry` around `Call`) carries the `raw` transcription, any marks, and
  issues, plus the parsed value — or null when the token couldn't be understood
  as a whole. Parse failure is thus one explicit, all-or-nothing signal, the
  inner parsed objects stay clean, and the marks and `raw` survive even a
  content-parse failure.
- **Validation never raises.** All checks — structural and bridge-semantic alike
  — run as pure functions that _return_ issues. Pydantic is configured so that
  even malformed content is captured rather than rejected (see
  [Why Pydantic](#why-pydantic)).

## VLM output

The vision model's job is faithful perception, not interpretation. It
transcribes what each cell shows; it does not parse bids, map circles to
"opponents," or normalize results. Its output is one flat object per board plus
a session header.

```json
{
  "event": "PABC mon",
  "date": "6/29",
  "boards": [
    {
      "board_number": "7",
      "vs": "3",
      "lead": "10S",
      "contract": "2H S +2",
      "auction": "(1N) 2H!",
      "notes": ""
    }
  ]
}
```

Every value is a string, transcribed as written — mistakes included. There is
deliberately **no score field**: the sheet's matchpoint estimate is not
trustworthy, and the traveller is authoritative (matchpoints are filled in at
reconciliation, and are simply absent for a no-traveller session).

The header carries `event` and `date`. `event` is stored raw; `date` is parsed
downstream, and the VLM is expected to emit it as numeric month/day (`6/29`),
normalizing whatever the human wrote ('June 9th', `6.23`, `June 9`). A human
records the date many ways; a VLM reasons through the variants far more easily
than a regex, so that burden sits here, not in the parser. The year is absent on
the sheet and inferred downstream against the scan date.

Our own pair is deliberately **not** transcribed. A pair is identified by number
and direction (sometimes a section too), not a bare number, and that identity is
recovered far more directly from the travellers — so it is resolved at
reconciliation, not read from the sheet. The opponent pair (`vs`) is still
transcribed per board: the reconciliation join needs it.

### Auction string syntax

The auction is a single faithful transcription of the bidding line, mirroring
how it is written on the sheet. The VLM emits the characters and these inline
markers; it does not interpret them.

- Calls are space-separated: `1C 1D 1N`.
- **Circled** (a call by the opponents) → parentheses: `(1D)`.
- **Boxed** (a call to discuss with partner) → square brackets: `[2N]`. A box
  may span several calls and may wrap circled ones: `[(2C)]`, `[2N 3C]`.
- **Alertable** (`!`) → kept as written, as a trailing mark: `2H!`. A `!`
  anywhere but the end isn't a valid alert and is flagged for review.
- **Announcement** → `_` for a subscript, `^` for a superscript, with the text
  as seen; a call may carry both: `1C_2`, `1N_SF`, `1H_S`, `1N^0_2`.
- **Double / redouble** → `*` / `**`, or the handwritten `x` / `xx`, each its
  own token: `(1H) * 2S`.
- **Scratched-out** calls → omitted by the VLM entirely.
- **Passes** → lowercase `p`, on the rare occasions they are written.

Glyph mistakes are expected and tolerated: a misread `3D` written `ED` is passed
through verbatim and flagged downstream, leaving the rest of the auction intact.

### Contract string

The contract cell is transcribed verbatim and parsed downstream. It encodes the
final contract, any penalty, the declarer, and the result together:

`<level><strain>[penalty]<declarer><result>`

- `2H S +2` — 2♥ by South, two tricks beyond the eight needed.
- `6H*W-1` — 6♥ **doubled** by West, down one. The penalty (`*`/`**`, or the
  handwritten `x`/`xx`) sits before the declarer.
- `3NT W +7` — notrump is written `N` or `NT`; both read the same.
- `PASSOUT`, any cell whose text contains 'pass' (`PASS`, `ALL PASS`), or a dash
  through the cell — no contract; the board is a passout.

The VLM extracts the characters faithfully and is prepared for the penalty
marker; segmenting the cell into fields is the parser's job.

## Parsing

A single, pure, unit-testable module turns VLM output into the canonical model.
It is the project's "interpretation layer": all bridge convention lives here,
not in the model and not in the VLM. It never raises; unparseable input yields a
null parsed value plus an `Issue`.

### Auction grammar

Tokenizing the auction is not a naive space-split, because a box can span
multiple space-separated calls. The grammar:

- A **box** `[ … ]` opens a to-discuss span covering every call inside it; the
  span may contain circled calls.
- A **circle** `( … )` wraps exactly one call.
- A **call core** is the remaining text: bid glyphs, an optional trailing `!`,
  an optional `_…` and/or `^…` announcement, or a standalone `*` / `**` / `p`.

The parser strips the structural markup — which is reliable, since it is
explicit in the string — into booleans, then parses the core. A bid core is
expected to match a level `1`–`7` and a strain (`C`/`D`/`H`/`S`, and notrump as
`N` or `NT`); anything else is kept as `raw` with an `unparseable_call` issue.

Worked example — the rank-legal string `1H (x) 2H! (2S) [3H] (p) p` parses to:

| Token  | by_opp | discuss | alert | kind   | level | strain | announcement | issue |
| ------ | ------ | ------- | ----- | ------ | ----- | ------ | ------------ | ----- |
| `1H`   | no     | no      | no    | bid    | 1     | H      | —            | —     |
| `(x)`  | yes    | no      | no    | double | —     | —      | —            | —     |
| `2H!`  | no     | no      | yes   | bid    | 2     | H      | —            | —     |
| `(2S)` | yes    | no      | no    | bid    | 2     | S      | —            | —     |
| `[3H]` | no     | yes     | no    | bid    | 3     | H      | —            | —     |
| `(p)`  | yes    | no      | no    | pass   | —     | —      | —            | —     |
| `p`    | no     | no      | no    | pass   | —     | —      | —            | —     |

An artificial-suit or notrump-range announcement (`1H_S`, `1N^0_2`) is decoded
by [Announcement decoding](#announcement-decoding) below; an unreadable core
like `ED` becomes an `unparseable_call` issue with the rest of the line intact.

### Announcement decoding

A call's `_` subscript and `^` superscript annotate its meaning; the parser maps
them to an `Announcement`. The markers are the vision model's faithful
transcription (see [Auction string syntax](#auction-string-syntax)); decoding
them is the parser's job.

- A subscript **strain letter** (`_S`) → `artificial_suit`, showing that strain.
- A subscript **digit** (`_2`) → `min_suit_length`, that many cards in the bid's
  own suit.
- `_SF` → `semi_forcing`; `_F` → `forcing`.
- A **superscript** is a notrump range: the superscript is the minimum and the
  subscript the maximum, each a teens value with the leading `1` implied, so
  `^0_2` is 10–12 and `^5_7` is 15–17. The two halves may be transcribed in
  either order — `^0_2` and `_2^0` are the same range. A `+` on the minimum
  (`^4+` is 'a good 14') sets `minimum_points_is_soft`; the floor (14) is kept
  and the `+` also survives in `raw`.
- Anything else unrecognized → `other`, raw preserved, so a novel form never
  fails.

Only an explicit annotation is decoded. What a bare, unannotated `1N` implies —
the club's assumed range — is not the parser's concern; the sheet spells a range
out only when it departs from that default.

### Contract parsing

The contract cell parses into a `Contract` and a `Result` together (they share
the one raw cell). `*`/`**` before the declarer set the penalty; the trailing
`±N` is normalized to `tricks_taken` (see
[Result normalization](#result-normalization)). `PASSOUT` or a struck-through
cell yields a null contract and result — the board is a passout.

| Raw cell  | level | strain | penalty | declarer | tricks_taken |
| --------- | ----- | ------ | ------- | -------- | ------------ |
| `2H S +2` | 2     | H      | none    | S        | 8            |
| `6H*W-1`  | 6     | H      | doubled | W        | 11           |
| `3N W +7` | 3     | NT     | none    | W        | 13           |
| `PASSOUT` | —     | —      | —       | —        | —            |

### Result normalization

The handwritten convention (`−N` = down N; `+N` = total tricks beyond book) and
its conversion to canonical `tricks_taken` are specified in
[spec.md](spec.md#notation-and-normalization). The normalizer needs the parsed
contract level to convert `−N`, so it runs after contract parsing. An off-by-one
here corrupts every downstream traveller comparison, so it is built and
unit-tested before anything depends on it.

## Canonical model

The stored, queryable shape. Expressed as Pydantic models; the JSON on disk is
their serialization. Bounded value sets are enums throughout.

The models are **frozen and deeply immutable**: every model inherits a frozen
base, and collection fields are `tuple`, not `list`, so a built record can't be
mutated in place and is hashable. A change to a parsed record is a new object,
not a mutation of the old one. The models derive nothing — every value,
including dealer and vulnerability, is set by the parser; Pydantic only holds
and (de)serializes.

Each written token sits in a **parse envelope**: a wrapper carrying the raw
transcription, any structural marks, and issues, plus the parsed value — or null
when the token couldn't be understood as a whole. The envelope makes parse
failure a single, all-or-nothing signal and keeps the inner parsed objects
clean, with no field-by-field optionality standing in for failure. The four
envelopes are `BoardNumber` (around a `Schedule`), `AuctionEntry` (around
`Call`), `Lead` (around `Card`), and `Outcome` (around a played contract or a
passout).

### Enums

- `Direction` — `N` / `E` / `S` / `W`.
- `Strain` — `C` / `D` / `H` / `S` / `NT`.
- `Suit` — `C` / `D` / `H` / `S`.
- `Rank` — `2`…`9`, `T`, `J`, `Q`, `K`, `A`.
- `Penalty` — `none` / `doubled` / `redoubled`.
- `CallKind` — `bid` / `pass` / `double` / `redouble`.
- `Vulnerability` — `none` / `NS` / `EW` / `both`.
- `AnnouncementType` — `artificial_suit` / `min_suit_length` / `forcing` /
  `semi_forcing` / `nt_range` / `other`.
- `IssueSeverity` — `low` / `medium` / `high`.

`Issue.code` is a plain string for now; it becomes an enum once the parser and
validation pass define the concrete code set (see
[Open questions](#open-questions-and-todos)).

### Session

- `session_key` — stable identifier derived from event and date, e.g.
  `pabc-mon-2026-06-29`; the filename and the reconciliation join. Null until
  ingest assigns it, downstream of parsing.
- `event` — raw header text.
- `date` — parsed date, or null with an issue if unparseable.
- `source` — provenance: the sheet image (path + content hash) and the
  travellers consulted.
- `boards` — the tuple of `Board`s.

Our own pair identity is intentionally not a field here: it is resolved from the
travellers at reconciliation, not read from the sheet (see
[VLM output](#vlm-output)).

### Board

- `number` — a `BoardNumber` envelope: the parsed board number and the dealer
  and vulnerability it fixes.
- `flagged_for_review` — true when the board number was circled.
- `opponent_pair` — their pair, parsed from the `Vs` cell to an int; null with
  an issue when unreadable.
- `opening_lead` — a `Lead` envelope, or null when no lead was recorded.
- `outcome` — an `Outcome` envelope (the contract cell), or null.
- `matchpoints` — traveller-sourced, filled at reconciliation; null until then
  and for no-traveller sessions.
- `auction` — an ordered tuple of `AuctionEntry`.
- `notes` — freetext cursive annotations (the inline questions), or null.
- `issues` — board-level issues.

A board's boxed calls aren't a separate field: each boxed call's `AuctionEntry`
carries `flagged_for_discussion`, and the "calls to discuss with partner" list
is a filter over the auction. This supersedes the earlier decision to fold boxes
into `notes`.

### BoardNumber

The envelope for the board-number cell.

- `raw` — the number as transcribed (`7`, or `l3` for a misread).
- `schedule` — a `Schedule` when the number was read and valid, or null when it
  was unreadable or invalid.
- `issues` — per-cell issues (e.g. `unreadable_board_number`).

The parsed value is all-or-nothing: a null `schedule` is the single signal that
the number couldn't be understood, with no partially known board. Either way the
board is stored and flagged for review — an unreadable number is a review item,
not a reason to drop the board, per
[nothing is garbage](#design-principle-nothing-is-garbage).

### Schedule

A resolved board number and the deal parameters it fixes. Present only inside a
`BoardNumber` whose parse succeeded, so every field is set together.

- `number` — the parsed board number.
- `dealer` — `Direction`, fixed by `number` under the standard 16-board cycle.
- `vulnerability` — `Vulnerability`, fixed by `number` under the same cycle.

The parser computes `dealer` and `vulnerability` from `number` (see
[Dealer and vulnerability](#dealer-and-vulnerability)); the models store them,
deriving nothing.

### AuctionEntry

The envelope for one written token of the auction. Marks live here, not on
`Call`, because they're read from reliable markup and survive a content-parse
failure — a circled but unreadable token is still known to be the opponents'.

- `raw` — the token exactly as transcribed, markup included (`(1N)`, `[(2C)]`,
  `1N^0_2`, `ED`).
- `by_opponents` — true when circled.
- `alerted` — true when annotated `!`.
- `flagged_for_discussion` — true when boxed.
- `call` — the understood `Call`, or null when the token couldn't be parsed.
- `issues` — per-token issues (e.g. `unparseable_call`).

### Call

The understood call — present only within an `AuctionEntry` whose parse
succeeded.

- `kind` — `CallKind`.
- `level` — `1`–`7` for bids; null for pass/double/redouble (a kind-driven
  absence, not a parse failure).
- `strain` — `Strain` for bids; null otherwise.
- `announcement` — an `Announcement`, or null.

### Announcement

- `raw` — the announcement text as seen (`S`, `2`, `SF`, `^0_2`).
- `type` — `AnnouncementType`; `other` when unrecognized, so a novel form never
  fails — it degrades to `other` carrying `raw`. It needs no envelope of its
  own.
- typed payload per type: `artificial_suit` carries the shown strain;
  `min_suit_length` the suit and minimum length; `nt_range` the min and max
  points, plus `minimum_points_is_soft` for a 'good N' (`^N+`) floor; `forcing`
  and `semi_forcing` need no payload.

### Lead

The envelope for the opening lead.

- `raw` — the lead as transcribed (`10S`, `QC`).
- `card` — the understood `Card`, or null on parse failure.
- `issues` — per-lead issues.

### Card

The understood card — whole only when both rank and suit were read.

- `rank` — `Rank`.
- `suit` — `Suit`.

### Outcome

The envelope for the contract cell. One cell yields both the contract and its
result, so they share a transcription and issue list.

- `raw` — the verbatim contract cell (`4S N +6`, `6H*W-1`, `PASSOUT`).
- `resolution` — a `kind`-tagged union, `PlayedContract` or `Passout`, or null
  when the cell couldn't be parsed. A passout is therefore an explicit
  understood state, distinct from an unparsed cell (null) — and the tag keeps
  the two distinct in the stored JSON, not just in the types.
- `issues` — per-cell issues.

`PlayedContract` bundles a `Contract` and its `Result`, both always present, so
"played" implies both. `Passout` is a marker with no payload.

### Contract

The played contract, present only when fully understood.

- `level` — `1`–`7`.
- `strain` — `Strain`.
- `declarer` — `Direction`.
- `penalty` — `Penalty`.

### Result

- `tricks_taken` — the canonical trick count. Making, overtricks, and
  undertricks are derived from it and the contract level; they aren't stored.

### Issue

The unit of "something to look at." Drives the review triage ranking; lives on
the envelope whose parse produced it, or on the board for board-level issues.

- `code` — a string identifier (an enum later).
- `severity` — an `IssueSeverity`.
- `message` — human-readable, with enough context to act on without the image.
- `location` — optional pointer to the offending field or auction index.

## Dealer and vulnerability

Both are pure functions of the board number under the standard 16-board cycle,
computed by the parser and stored in the `Schedule` — never extracted, never
derived by the models. They are present exactly when the `Schedule` is, i.e.
when the number was read and valid. Per the resolution in
[spec.md](spec.md#open-questions), there is no printed-column checksum: the
computed value is authoritative on its own, and board-numbering errors surface
through traveller reconciliation instead. The computation is table-driven and
tested across a full cycle.

## Validation

A non-raising pass over a built board: pure functions that return `Issue`s,
composed into one `find_issues(board) -> list[Issue]`. Failures never abort;
they rank the board in the review queue. The checks, by concern:

- **Content well-formedness** — each `Call`, the lead, and the contract parsed
  to canonical values; `level` in `1`–`7`; `tricks_taken` in `0`–`13`. A failure
  here means a `raw` value the parser couldn't resolve.
- **Auction legality** — bid rank is non-decreasing across successive bids (a
  pass/double/redouble does not advance rank); the last non-pass call equals the
  stated contract; the declarer is derivable from the auction and consistent
  with the contract's declarer.
- **Card legality** — the opening lead is a real card.

Each check owns an `IssueCode` and assigns a severity. Because the pass operates
on a fully-built board, it is tested with hand-constructed boards — legal ones
asserting no issues, and deliberately broken ones (rank reversal, contract
disagreeing with the last call, an impossible lead) asserting the exact issue —
with zero OCR involved.

## Why Pydantic

With every bridge check moved into the parser and the validation pass, Pydantic
is **not** the gatekeeper for content. Its job is narrower and honest:

- **JSON ↔ typed object (de)serialization** of a deeply nested structure
  (Session → Board → AuctionEntry → Call, alongside `Lead`, `Outcome`, and their
  contents), with coercion (strings → `date`, ints, enums, nested models, the
  `kind`-tagged `Outcome` union) for free. This is the main earning, and exactly
  what a JSON-on-disk, DB-bound pipeline needs.
- **Skeleton typing** — the bones are real types (`boards: tuple[Board, ...]`,
  `auction: tuple[AuctionEntry, ...]`, `number: BoardNumber`), so downstream
  code and the validation pass can rely on shape without re-checking it.

It is configured so content never raises: every parsed value is optional — an
envelope's parsed value, and the header `date` parsed straight into `Session` —
so a misread is captured as a null rather than rejected, and the genuinely
malformed skeleton — the rare case where the VLM returns something that isn't
shaped like a board at all — is contained by parsing board-by-board, so one
broken board is captured and flagged while the rest succeed. The errors Pydantic
catches are _shape_ errors ("this isn't a board record"), never _content_ errors
("this isn't legal bridge") — those belong to validation.

The alternative considered was stdlib `dataclasses` plus hand-written JSON
mapping: viable, but it hand-rolls the nested (de)serialization and coercion
Pydantic does declaratively, which this pipeline genuinely needs. msgspec is
faster but offers nothing here, since throughput is irrelevant at one or two
sheets per week and we use none of its validation.

## Testing the models

These models are plain data holders — no validators, computed fields, or custom
serializers — so constructing one and reading a field back tests Pydantic, not
us. Their tests pin only what is genuinely ours: the serialization contract,
chiefly the `kind`-tagged `Outcome` union keeping a played contract, a passout,
and an unparsed cell distinct in the JSON. Turning VLM strings into these models
is the parser's behaviour, and is tested there.

## Open questions and TODOs

- **VLM extraction prompt** — the system prompt that elicits the
  [VLM output](#vlm-output) faithfully (transcribe-don't-interpret, the auction
  and contract syntax, scratch-outs dropped). To be written when extraction is
  built; deferred for now.
- **Announcement type set** — `AnnouncementType` will grow as new announcement
  forms appear; `other` absorbs the unrecognized in the meantime.
- **Issue codes and severities** — the concrete `IssueCode` set and each check's
  severity firm up as the validation pass and the review triage are built
  together.

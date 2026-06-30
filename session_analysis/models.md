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

- **Every parsed field carries its `raw` source.** Parsing is best-effort: on
  success the structured fields are populated; on failure they are null, an
  `Issue` is logged, and `raw` preserves exactly what the VLM saw.
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
  "pair": "6",
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

The header fields are strings too; `date` and `pair` are parsed downstream like
everything else.

### Auction string syntax

The auction is a single faithful transcription of the bidding line, mirroring
how it is written on the sheet. The VLM emits the characters and these inline
markers; it does not interpret them.

- Calls are space-separated: `1C 1D 1N`.
- **Circled** (a call by the opponents) → parentheses: `(1D)`.
- **Boxed** (a call to discuss with partner) → square brackets: `[2N]`. A box
  may span several calls and may wrap circled ones: `[(2C)]`, `[2N 3C]`.
- **Alertable** (`!`) → kept as written: `2H!`.
- **Announcement** → `_` for a subscript, `^` for a superscript, with the text
  as seen; a call may carry both: `1C_2`, `1N_SF`, `1H_S`, `1N^0_2`.
- **Double / redouble** → `*` / `**`, each its own token: `(1H) * 2S`.
- **Scratched-out** calls → omitted by the VLM entirely.
- **Passes** → lowercase `p`, on the rare occasions they are written.

Glyph mistakes are expected and tolerated: a misread `3D` written `ED` is passed
through verbatim and flagged downstream, leaving the rest of the auction intact.

### Contract string

The contract cell is transcribed verbatim and parsed downstream. It encodes the
final contract, any penalty, the declarer, and the result together:

`<level><strain>[*|**]<declarer><result>`

- `2H S +2` — 2♥ by South, two tricks beyond the eight needed.
- `6H*W-1` — 6♥ **doubled** by West, down one. The `*` is the penalty, sitting
  before the declarer.
- `PASSOUT` (or a dash through the cell) — no contract; the board is a passout.

The VLM extracts the characters faithfully and is prepared for the `*`/`**`
penalty marker; segmenting the cell into fields is the parser's job.

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
expected to match `[1-7][CDHSN]`; anything else is kept as `raw` with an
`unparseable_call` issue.

Worked example — the string `(1D) 1H_S * 2N! [(2C)] 1N^0_2 ED` parses to:

| Token    | by_opp | discuss | alert | kind   | level | strain | announcement                 | issue              |
| -------- | ------ | ------- | ----- | ------ | ----- | ------ | ---------------------------- | ------------------ |
| `(1D)`   | yes    | no      | no    | bid    | 1     | D      | —                            | —                  |
| `1H_S`   | no     | no      | no    | bid    | 1     | H      | artificial_suit, shows S     | —                  |
| `*`      | no     | no      | no    | double | —     | —      | —                            | —                  |
| `2N!`    | no     | no      | yes   | bid    | 2     | NT     | —                            | —                  |
| `[(2C)]` | yes    | yes     | no    | bid    | 2     | C      | —                            | —                  |
| `1N^0_2` | no     | no      | no    | bid    | 1     | NT     | nt_range, 10–12 (raw `^0_2`) | —                  |
| `ED`     | no     | no      | no    | —      | —     | —      | —                            | `unparseable_call` |

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

Content-leaf fields are **optional** — a null means "the VLM saw something, but
the parser couldn't make it canonical," and the adjacent `raw` holds what it
saw. This is what lets a malformed value be stored rather than rejected.

### Enums

- `Direction` — `N` / `E` / `S` / `W`.
- `Strain` — `C` / `D` / `H` / `S` / `NT`.
- `Suit` — `C` / `D` / `H` / `S`.
- `Rank` — `2`…`10`, `J`, `Q`, `K`, `A`.
- `Penalty` — `none` / `doubled` / `redoubled`.
- `CallKind` — `bid` / `pass` / `double` / `redouble`.
- `Vulnerability` — `none` / `ns` / `ew` / `both`.
- `AnnouncementType` — `artificial_suit` / `min_suit_length` / `semi_forcing` /
  `nt_range` / `other`.
- `IssueSeverity` — `low` / `medium` / `high`.
- `IssueCode` — the closed set of check identifiers (see
  [Validation](#validation)).

### Session

- `session_key` — stable identifier derived from event and date, e.g.
  `pabc-mon-2026-06-29`; the filename and the reconciliation join.
- `event` — raw header text.
- `date` — parsed date, or null with an issue if unparseable.
- `pair_number` — our pair.
- `source` — provenance: the sheet image (path + content hash) and the
  travellers consulted.
- `boards` — the list of `Board`s.

### Board

- `board_number` — parsed int; the dealer/vul source.
- `dealer` — `Direction`, **computed** from `board_number` (never extracted; see
  [Dealer and vulnerability](#dealer-and-vulnerability)).
- `vulnerability` — `Vulnerability`, **computed** from `board_number`.
- `flagged_for_review` — true when the board number was circled.
- `opponent_pair` — parsed from the `Vs` string, or null.
- `opening_lead` — a `Card`, or null.
- `contract` — a `Contract`, or null for a passout.
- `result` — a `Result`, or null for a passout.
- `matchpoints` — traveller-sourced, filled at reconciliation; null until then
  and for no-traveller sessions.
- `auction` — an ordered list of `Call`s.
- `notes` — freetext cursive annotations (the inline questions), or null.
- `contract_cell_raw` — the verbatim contract cell, the shared source for
  `contract` and `result`.
- `issues` — board-level validation issues.

A board's boxed calls are not a separate field: each boxed call carries
`flagged_for_discussion` (below), which is the queryable "calls to discuss with
partner" list — a filter over the auction. This supersedes the earlier spec
decision to fold boxes into `notes`.

### Call

- `raw` — the call token exactly as transcribed, markup included (`(1N)`,
  `[(2C)]`, `1N^0_2`, `ED`).
- `kind` — `CallKind`, or null if unparseable.
- `level` — `1`–`7`, for bids; null otherwise or on failure.
- `strain` — `Strain`, for bids; null otherwise or on failure.
- `by_opponents` — true when circled. Reliable structural markup, not a guess.
- `alerted` — true when annotated `!`.
- `flagged_for_discussion` — true when boxed.
- `announcement` — an `Announcement`, or null.
- `issues` — per-call issues (e.g. `unparseable_call`).

### Announcement

- `raw` — the announcement text as seen (`S`, `2`, `SF`, `^0_2`).
- `type` — `AnnouncementType`; `other` when unrecognized, so a novel form never
  fails — it degrades to `other` carrying `raw`.
- typed payload per type: `artificial_suit` carries the shown strain;
  `min_suit_length` the suit and minimum; `nt_range` the min and max points;
  `semi_forcing` needs no payload.

### Contract

- `level` — `1`–`7`, or null.
- `strain` — `Strain`, or null.
- `penalty` — `Penalty`.
- `declarer` — `Direction`, or null.
- `issues` — per-contract issues.

The shared raw cell lives on the board (`contract_cell_raw`), since one cell
yields both `Contract` and `Result`.

### Result

- `tricks_taken` — `0`–`13`, or null on failure.
- `issues` — per-result issues.

Making, overtricks, and undertricks are derived from `tricks_taken` and the
contract level; they are not stored.

### Card

- `raw` — the lead as transcribed (`10S`, `QC`).
- `rank` — `Rank`, or null.
- `suit` — `Suit`, or null.
- `issues` — per-card issues.

### Issue

The unit of "something to look at." Drives the review triage ranking.

- `code` — an `IssueCode`.
- `severity` — an `IssueSeverity`.
- `message` — human-readable, with enough context to act on without the image.
- `location` — optional pointer to the offending field or auction index.

## Dealer and vulnerability

Both are pure functions of the board number under the standard 16-board cycle,
computed and stored — never extracted. Per the resolution in
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

- **JSON ↔ typed object (de)serialization** of a five-level nested structure
  (Session → Board → Call / Contract / Result / Announcement / Card), with
  coercion (strings → `date`, ints, enums, nested models) for free. This is the
  main earning, and exactly what a JSON-on-disk, DB-bound pipeline needs.
- **Skeleton typing** — the bones are real types (`boards: list[Board]`,
  `auction: list[Call]`, `board_number: int`), so downstream code and the
  validation pass can rely on shape without re-checking it.

It is configured so content never raises: leaf fields are optional, and the
genuinely malformed skeleton — the rare case where the VLM returns something
that isn't shaped like a board at all — is contained by parsing board-by-board,
so one broken board is captured and flagged while the rest succeed. The errors
Pydantic catches are _shape_ errors ("this isn't a board record"), never
_content_ errors ("this isn't legal bridge") — those belong to validation.

The alternative considered was stdlib `dataclasses` plus hand-written JSON
mapping: viable, but it hand-rolls the nested (de)serialization and coercion
Pydantic does declaratively, which this pipeline genuinely needs. msgspec is
faster but offers nothing here, since throughput is irrelevant at one or two
sheets per week and we use none of its validation.

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

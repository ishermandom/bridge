# Session analysis — scoresheet digitization

## Goal

Turn a night of bridge into something to learn from, automatically. The
envisioned pipeline (see the repository README's "Session analysis" section)
scans a handwritten scoresheet, fetches the official hand records, and compares
the contracts and results reached against double-dummy analysis — surfacing the
deals where the table diverged most from optimal play.

This spec covers the **first step**: digitizing a handwritten scoresheet into a
structured, canonical record that downstream analysis can consume. It defines
the data model, the extraction approach, and the human-review path that gets a
night's sheet into that model accurately.

Language: Python, consistent with the rest of the repository's tooling.

## Scope

In scope — the full digitization pipeline, end to end:

- **Ingest**: get a sheet photo from an Android phone onto the Mac.
- **Extraction**: read the sheet's handwriting into the data model.
- **Validation**: enforce bridge legality and internal consistency.
- **Normalization**: convert the handwritten result convention to canonical.
- **Reconciliation**: cross-check against the official travellers.
- **Review**: a human corrects what the machine got wrong.
- **Export**: emit the canonical record for the analysis stage.

Out of scope (separate, later projects that consume this stage's output):

- The double-dummy comparison and "where did the table diverge" analysis.
- The queryable database and the session-analysis browsing UI. This stage's
  review UI is deliberately minimal and standalone (see [Review](#review)); it
  is not the foundation for the eventual analysis UI.

## Source-of-truth model

The official **traveller is the source of truth** for everything it records:
board, contract, declarer, result, matchpoints, and opponent pair. The **sheet
is the sole source for what travellers lack**:

1. the full **auction**,
2. the **opening lead**,
3. **freetext annotations** — the inline questions ("why no club switch?") and
   the boxed bids flagged for partnership review,
4. the **personal review flags** — circled board numbers.

Two travellers are available per session, both saved as local HTML: the ACBL
Live traveller (e.g. `1472071.html`) and the club website capture (e.g.
`R260629M.html`). The ACBL capture carries an `opening_lead` field, but this
club leaves it empty for every row — so in practice the opening lead is
sheet-only. Design for the traveller existing most weeks, but not all.

Corollaries:

- **Dealer and vulnerability are computed, never read.** Both are fixed
  functions of the board number under the standard 16-board cycle. Computing
  them removes a column from the extraction burden and yields a free integrity
  check: if the computed dealer/vul disagrees with what the sheet implies, the
  board numbering is off. This check works even with no traveller.
- **The auction is the irreducible review burden.** The traveller verifies its
  _endpoints_ — the last call equals the contract, and the declaring seat is
  consistent — but nothing external checks the _sequence_. The auction is at
  once the hardest extraction target and the one field review cannot lean on
  external truth for. Budget accuracy and human attention here.

## Pipeline

1. **Ingest** — Android scan lands on the Mac (see [Ingest](#ingest)).
2. **Extract** — the scan image goes to a vision model, which emits the data
   model as JSON (see [Extraction](#extraction)).
3. **Validate** — Pydantic plus bridge-legality checks (see
   [Validation](#validation)).
4. **Normalize** — convert the handwritten result convention to canonical
   `tricks_taken` (see
   [Notation and normalization](#notation-and-normalization)).
5. **Reconcile** — join to the travellers, cross-check recoverable fields, and
   surface likely row swaps (see [Reconciliation](#reconciliation)).
6. **Review** — a human accepts or corrects flagged fields, with row-level
   fixups as first-class operations (see [Review](#review)).
7. **Export** — the canonical record is written for the analysis stage (see
   [Export and storage](#export-and-storage)).

## Data model

One session is one record. The canonical on-disk format is **JSON, one file per
session** — directly machine-readable and the interchange format the analysis
stage reads. The eventual home is a queryable database with a browsing UI; the
model is designed to port cleanly into tables, but the **final storage format is
an open question** (see [Open questions](#open-questions)). Treat JSON as the
stable interchange contract, not necessarily the stable store.

The field-level schema — the canonical record, the vision model's output
contract, the parser between them, and the validation pass — is specified in
[models.md](models.md). At pipeline altitude:

- **One session is one record**: a footer (event, date, provenance) plus a list
  of board records. Our own pair identity is not read from the sheet — it is
  resolved from the travellers at reconciliation (see
  [models.md](models.md#vision-model-output)).
- **Each board** carries its number; the computed dealer and vulnerability; the
  opening lead; the contract, penalty, declarer, and result (canonicalized to
  tricks taken); the auction as an ordered list of calls; the freetext notes;
  and the review flags — a circled board number, and per-call "discuss with
  partner" markers lifted from boxed bids. Matchpoints are traveller-sourced and
  filled at reconciliation.
- **Nothing is discarded as garbage**: each written token sits in an envelope
  beside its raw text, so a misread is captured and flagged, never rejected (see
  [Validation](#validation)).

Pydantic owns the record's shape and JSON (de)serialization, not content
validation — see [models.md](models.md#why-pydantic) for that boundary.

## Notation and normalization

The sheet's result convention, confirmed with the user:

- `−N` means **down N** — N tricks short of the contract.
- `+N` means **N tricks beyond book**, where book is 6 — an absolute trick
  count, not overtricks on the contract. So `4S N +6` is 12 tricks (6 + 6), i.e.
  4♠ making two overtricks; `3N W +7` is 13 tricks.

The normalizer converts either form to canonical `tricks_taken`:

- `+N` → `tricks_taken = 6 + N`.
- `−N` → `tricks_taken = (level + 6) − N`.

The traveller uses a third convention — `4 S` / `+2` (overtricks on the
contract). The normalizer bridges all three through `tricks_taken`: `4S +6`
(sheet) and `4 S +2` (traveller) both yield 12, and reconciliation compares on
that.

An off-by-one here silently corrupts every downstream traveller comparison, so
the normalizer is **built and unit-tested before anything that depends on it**
(see [Build order](#build-order)).

## Extraction

The sheet's handwriting is read by a vision model via **Claude Code in headless
mode**, on the existing Claude subscription — no separate API billing.

- **Model**: `claude-sonnet-5` (released 2026-06-30; strong vision, 1M context,
  live in Claude Code). A **single model, no escalation fallback** to start —
  the digest's Sonnet-workhorse-plus-Opus-escalation tiering is deliberately
  deferred as premature for 1–2 sheets/week. Revisit if accuracy on the auction
  column proves insufficient.
- **Invocation**: `claude -p` (non-interactive); see
  `vision_model_invocation.py`. The default agentic-coding system prompt is
  **fully replaced** via `--system-prompt` with a prompt scoped to scoresheet
  transcription. `--setting-sources ""` and
  `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` keep the run from being
  polluted by `CLAUDE.md`, hooks, or MCP servers — the isolation `--bare` was
  originally meant to give. `--bare` itself turned out not to work here: it
  requires `ANTHROPIC_API_KEY`/`apiKeyHelper` or `CLAUDE_CODE_OAUTH_TOKEN`, and
  on this personal (non-org) account, even a known-good, currently-valid access
  token supplied via `CLAUDE_CODE_OAUTH_TOKEN` 401s under it — found by
  live-testing the CLI while chasing an auth failure. Plain `-p` with normal
  OAuth reaches the same low-overhead floor without that broken path. Scan
  images are embedded as base64 in a `--input-format stream-json` message rather
  than read through the `Read` tool — one turn instead of two, and no
  tool-definition token cost. `stream-json` input requires
  `--output-format stream-json` in turn, so the response is a `result` event
  parsed out of a JSON-lines stream rather than a single `--output-format json`
  envelope; `--json-schema` keeps that event's payload schema-conformant JSON.
- **Input format: labeled per-row strips at native resolution.** The CLI
  downscales a full 12MP scan to ~56% linear before the model sees it, and a
  live comparison on the 6/29 sheet showed every resolution-class error (a
  misread contract digit, dropped announcements, box-vs-circle swaps on dense
  rows) vanishing when the sheet arrives as native-resolution crops instead — at
  lower cost than the full-sheet run ($0.21 vs $0.29). The request is an ordered
  sequence of labeled parts: one crop per printed board row, each preceded by a
  text label naming its printed row, then the footer crop. Three details are
  load-bearing, found by live experiment: each crop includes the printed `Bd`
  column (without it the model substitutes the adjacent `Vs` number), the labels
  fix board identity, and the prompt says explicitly to emit blank rows. Per-row
  is the tile size because the review UI needs per-row crops regardless, so
  row-precision geometry exists either way; coarser bands would save only the
  labeling machinery.
- **The scan is dewarped from its own printed grid before anything else reads
  it.** The live 6/29 scan (a raw phone photo) showed why: perspective slants
  the top rules ~1.5 row pitches across the sheet's width, tapering to flat at
  the bottom — no straight horizontal profile or straight crop survives that,
  and the prototype's straight strips worked only because the transcribed
  columns cluster where the drift is small. Narrow column slices each resolve
  the rules sharply; the fitted top/bottom rule lines and side border lines
  intersect into the grid's corner quad; and a true perspective transform (not
  PIL's bilinear `QUAD`, which measurably under-corrects mid-grid) maps the
  quad, extended with margins for footer and padding, to an upright rectangle at
  native scale. This supersedes the earlier reliance on the scanner app's
  perspective correction (see Ingest): good capture still helps, but correctness
  no longer depends on it.
- **Row geometry is detected per scan in dewarped space, and padding is the
  consumer's job.** Rule positions are per-rule medians across the column
  slices' chains — a full-width profile stays blind to a rule that page curl
  still drifts a fraction of a pitch, while each slice sees it sharply. The grid
  is identified structurally: the longest chain of near-uniform-pitch dips,
  skipping handwriting's interloper dips. The row count is not configured but
  voted — each column slice's chain length votes and the modal count wins, so
  forms with more or fewer rows resolve unchanged, and a slice that chained a
  ghost rule (the footer's printed guide underlines) is outvoted; a tie whose
  two readings end at the same bottom rule resolves to the longer one, since the
  shorter is the same grid missing top rows. Chained rows that aren't board rows
  are handled by kind: partial-width lines (the v4 form's scale charts above the
  grid, footer guide underlines below) are trimmed by ink coverage — a true grid
  rule spans the sheet's full width — while v4's board-pitch printed header row
  stays, and the prompt has the model transcribe its strip as a blank row.
  Validated on a rendered blank v4 form, clean and synthetically degraded (the
  committed fixture in `testdata/`). The result is a typed `SheetGeometry` of
  tight rule-to-rule row boxes — the footer region is derived from them, not
  stored — persisted with the source quad alongside the processed session:
  extraction cuts strips from it, a voting rerun reuses the same strips, and the
  review UI crops from it. Handwriting bleeds past the printed rules and curl
  leaves residual drift, so each consumer pads the tight boxes at cut time —
  extraction expands each strip by a fraction of the row pitch into its
  neighbors, and the prompt's "transcribe the row whose middle line the strip
  shows" rule disambiguates the duplicated content that padding creates.
- **Extraction job is mechanical.** The model emits one flat, string-valued
  object per board — the auction as a single faithful transcription with inline
  markup (parens, `!`, `_`/`^`, `*`, `[ ]`), the contract cell verbatim, and the
  lead and footer as written. It does not parse bids, map circles to
  "opponents," or normalize results; all of that is the downstream parser's job.
  The full output contract and syntax are in
  [models.md](models.md#vision-model-output). Keeping the model's job to
  transcription minimizes schema-conformance failures and keeps interpretation
  testable without it.
- Score is **not** extracted (estimated on the sheet; traveller-authoritative),
  and dealer/vul are **not** extracted (computed). Both are stated in the prompt
  to keep the model off redundant columns.

## Validation

After extraction and parsing, before reconciliation, each board runs through a
**non-raising validation pass**: pure functions that _return_ issues rather than
abort, so a flaw flags the board for review instead of failing the parse. The
checks — content well-formedness (each call, lead, and contract resolved to
canonical values), auction legality (rank monotonicity, contract equals the last
call, declarer derivable and consistent), and card legality — are specified in
[models.md](models.md#validation).

Each issue carries a severity that feeds the review triage ranking (see
[Review](#review)). Pydantic catches only _shape_ errors at construction; a
genuinely malformed board is contained by parsing board-by-board, never lost.
There is no dealer/vul integrity check — dealer/vul are computed-only (see
[Open questions](#open-questions)), so board-numbering errors surface through
reconciliation instead.

## Reconciliation

Join the digitized session to its travellers on `session_key` plus per-board
content, and cross-check the traveller-recoverable fields (contract, declarer,
result, matchpoints) against the sheet. The match recovers both pair identities
(ours and the opponents'), which the sheet does not record. Disagreement raises
a board's review priority.

Row-order errors are the expected failure mode (the user swapped boards 20 and
21 on the 6/29 sample). Detect them with a **best-alignment permutation** of
sheet rows against traveller boards: if sheet row N matches traveller board M
and vice versa, surface a "likely swap." **Suggest, never auto-apply** — two
boards with identical results are indistinguishable, so a human confirms. The
dealer/vul integrity check is a second, traveller-independent swap signal.

Reconciliation is best-effort, not required. When no traveller exists for a
session — some sessions ship only paper hand records (see
[Open questions](#open-questions)) — the sheet stands alone: every traveller
cross-check is skipped rather than failing, and the sheet plus computed
dealer/vul carry the record. The pipeline must run to completion with zero
travellers.

## Manual fixups

Some corrections the machine cannot infer. Row-level operations — **swap,
renumber, reorder** — are first-class in the review UI, two keystrokes each, so
the fix works whether or not auto-detection caught it. The board-20/21 swap is
the concrete known case.

## Ingest

Capture is from an **Android phone**; the scanner app and the phone-to-Mac
transport are **not yet chosen** (see [Open questions](#open-questions)).
Candidate scanners — the Google Drive scanner, Microsoft Lens, or a thin app
over ML Kit's document scanner — all do on-device edge detection and perspective
correction. Whichever is used, **retake a bad scan at the table**: the on-device
preview makes a retake cheap, and a flaw found after the sheet is gone is
unrecoverable.

The two candidate transports and their tradeoff:

- **Google Drive for Desktop** in mirror / "available offline" mode. Drive
  integration is already available in this environment. Gotcha: Drive for
  Desktop defaults to **online-only placeholders** — a watcher then sees
  zero-byte stubs, not image bytes, and fails confusingly. The `BridgeSheets/`
  folder must be set to mirror.
- **Syncthing** — peer-to-peer, always real bytes, sidesteps the placeholder
  gotcha, at the cost of a sync daemon on both ends.

Whichever is chosen:

- **Convention**: one sheet is one scan file; multiple pages allowed (the
  scanner's native multi-page container absorbs glare and binding splits with no
  pipeline logic). The scanner's on-device perspective correction improves
  capture quality but is no longer load-bearing — extraction dewarps from the
  printed grid itself (see Extraction); PDF pages are rasterized as needed.
- **Self-naming**: the footer (event, date) is read first so the file names
  itself by session key — no manual tagging. The key is confirmed in review
  before it commits to the filesystem.
- **Spine**: `inbox/` → `processed/<session-key>.json` + image → `archive/`.
  Idempotent on footer plus content hash, so re-scanning a sheet is a no-op.
- **Trigger**: an explicit "process inbox" command, not a watcher daemon. At
  this volume a silent daemon debugged twice a year is more total friction than
  a one-tap trigger, and failures should be visible rather than silent.

## Review

Ingest happens once per sheet; **review touches every flagged field on every
sheet**, so it dominates total friction — invest here, not in ingest automation.
The review tool is **minimal and standalone**: its only job is correcting this
stage's extraction. It is not the eventual session-analysis UI.

- **Triage-ranked, not linear.** Each field carries a risk score combining model
  confidence, validation failure, traveller disagreement, illegality, and the
  auction's inherent unverifiability. The reviewer works the top of the stack
  first.
- **Image crop beside the parsed value**, with keyboard accept/fix. Surfacing
  the highest-risk checks beats fatiguing character-by-character verification.
- Row-level fixups (swap/renumber/reorder) are first-class, per
  [Manual fixups](#manual-fixups).
- The tool **auto-opens (or notifies) after a sheet is processed**, so finishing
  is one launch plus a few keystrokes rather than a context switch.
- A thin local app with the image beside the field is the point — not a CLI.
  Concrete tech (e.g. FastAPI + htmx, or Gradio) is a follow-up decision.

## Export and storage

The reviewed, canonical session is written as `processed/<session-key>.json`,
the interchange contract the analysis stage reads. The eventual queryable
database and browsing UI consume the same canonical shape; migrating JSON files
into that store is a later step and does not change this stage's output
contract.

## Traveller captures and PII

Traveller HTML and scoresheet photos contain **other club members' names and
results**. They are kept local-only, never committed — consistent with the
existing `club_sites/palo_alto/fixtures/raw/` gitignore. Captures live under
`session_analysis/travellers/`, which is gitignored. Example scoresheet photos
(for reference while building extraction) live in the sibling `bridge-private`
repo's `scoresheets/` directory, kept out of this public repo for the same
reason.

The captures are saved-from-the-browser HTML against third-party servers (ACBL
Live, the club site). Eventually this stage should **archive and index the
travellers locally** so access doesn't depend on those servers staying up — a
durable local store keyed by session, parsed once rather than re-fetched. The
raw HTML stays out of git; the local index/store is a separate decision (see
[Open questions](#open-questions)).

## Testing strategy

- **Notation normalizer** — pure logic, unit-tested exhaustively first (makes,
  overtricks, all undertrick depths, the three conventions), before any code
  depends on it. This is the highest-leverage test in the project.
- **Legality validator** — unit-tested with legal and deliberately illegal
  auctions (rank reversal, contract/last-call mismatch, bad declarer) and bad
  cards; testable with zero OCR.
- **Dealer/vul computation** — table-driven test across a full 16-board cycle.
- **Reconciliation/swap detection** — fixtures with a known swap (the 6/29
  sample) assert the swap is _suggested_, and identical-result boards assert no
  false auto-apply.
- **Extraction** — not unit-tested against a live model; exercised through
  fixtures and the review loop. Use placeholder member data in any committed
  fixture.

## Build order

The first two stages are pure logic, testable with zero OCR, and de-risk
everything downstream:

1. Notation normalizer plus its unit tests.
2. Pydantic models, the dealer/vul computation, and the non-raising validation
   pass.
3. Extraction: the headless invocation and the mechanical transcription prompt.
4. Parser: vision model strings → canonical model (auction grammar, contract
   cell, announcements).
5. Reconciliation and swap detection against traveller fixtures.
6. Ingest spine and the "process inbox" trigger.
7. Review UI.

## Open questions

- **Final storage format** — JSON is the interchange contract; the durable store
  (most likely SQLite for a local queryable database, but unconfirmed) and its
  schema are to be decided when the analysis UI is designed.
- **Scanner app and transport** — Android scanner choice and Drive-mirror vs.
  Syncthing, per [Ingest](#ingest).
- **Model escalation** — whether a stronger-model fallback for low-confidence
  auction rows is worth adding, decided empirically once single-model accuracy
  is observed.
- **Review UI tech and interaction** — the concrete framework, keybindings, and
  commit semantics, pinned down when the UI is built.
- **Local traveller archive and index** — the durable local store and index of
  traveller HTML described in
  [Traveller captures and PII](#traveller-captures-and-pii): its schema, the
  parse-once strategy, and how it keys to sessions.
- **Paper hand records as a traveller source** — some sessions have no digital
  traveller, only paper hand records (occurred as recently as the week before
  this spec). Near-term, the pipeline must degrade gracefully with no traveller
  at all (see [Reconciliation](#reconciliation)); eventually it should support
  digitizing paper hand records as an alternative source of the recoverable
  fields.

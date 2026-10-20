# Session analysis — measurements

The dated results that decisions in [spec.md](spec.md) rest on: what was run,
what it showed, and what it cost. The spec records each decision and why, and
cites the section here that holds its evidence. The results live apart from the
decisions because they age: a new release, a CLI update, or a change to the
pipeline can leave any of them describing something that no longer runs. Most
come from the harness in [scratch/README.md](scratch/README.md), which says how
to re-run them.

## How entries are kept {#pruning}

- **Group entries by the decision they support**, one section per decision, so
  that a question such as "why Opus?" lands in one place.
- **Open each entry with its provenance**: the date, the sheets, the releases
  and effort, and how many runs. That line is what lets a reader judge whether
  the entry has gone stale.
- **Prune an entry once a newer measurement answers the same question.** Delete
  it rather than keep it as history; git keeps every version. A release falling
  out of use does not by itself retire an entry: Opus 5's figures stay as the
  baseline its successors are measured against.

## Sheets measured {#sheets}

- **The 6/29 sheet**:
  `bridge-private/session_analysis/scoresheets/samples/PXL_20260630_191216837.jpg`,
  a raw phone photo, and the only real sheet among the samples. It has no
  session record, so the 2026-10-10 model comparison judged it against a key
  assembled from runs: an Opus 5.5 run agreeing with the 40 runs of Opus 5.5 and
  Sonnet 5.5 at `high` on every cell where most of those runs agree. The
  exceptions are board 1's declarer, which the travellers settle as West, and
  board 17's `2D_H`, the only reading of that call that parses.
- **The 9/24 sheet**:
  `bridge-private/session_analysis/scoresheets/archive/862caf5b70a4-Scanned_20260924-1511.pdf`,
  a scanner app's PDF. Its session record, reconciled and reviewed with the
  user, is the answer key for `scratch/settled_session_comparison.py`.

Both sheets' strip sets, every run behind the 2026-10-10 entries, and both
answer keys are kept as the comparison's stored workload, so a later measurement
adds only its own runs (scratch/README.md #stored-workload).

## Model choice {#model-choice}

Supports the **Model** bullet in spec.md #extraction.

- **Opus 5, Opus 5.5, Sonnet 5.5 and Haiku 5.5** (2026-10-10, the 6/29 and 9/24
  sheets, one strip set each, 10 runs of each setting per sheet; the Opus
  releases at `high` only, Sonnet 5.5 and Haiku 5.5 at every effort from `low`
  to `max`): each run was judged cell by cell against the sheet's answer key,
  and each sweep's two runs were voted as ingest votes them. Per sheet of about
  28 boards, averaged over both sheets:

  | Setting                | Cost per sheet | Misread cells per run | Boards sent to review | Wrong cells past the vote |
  | ---------------------- | -------------: | --------------------: | --------------------: | ------------------------: |
  | Opus 5.5 at `high`     |         \$0.33 |                   1.1 |                   0.7 |                       0.6 |
  | Sonnet 5.5 at `xhigh`  |         \$0.20 |                   1.5 |                   0.8 |                       0.8 |
  | Sonnet 5.5 at `max`    |         \$0.80 |                   1.2 |                   0.8 |                       0.7 |
  | Sonnet 5.5 at `high`   |         \$0.17 |                   2.0 |                   1.3 |                       1.0 |
  | Opus 5 at `high`       |         \$0.45 |                   2.0 |                   0.8 |                       1.2 |
  | Sonnet 5.5 at `medium` |         \$0.13 |                   7.4 |                   6.4 |                       0.9 |
  | Sonnet 5.5 at `low`    |         \$0.14 |                   8.2 |                   9.5 |                       0.6 |
  | Haiku 5.5, any effort  |  \$0.01–\$0.07 |               5.2–6.9 |               3.6–5.8 |                   2.6–2.7 |
  - **Misses every setting shares**: most wrong cells past the vote, in every
    setting, are two cells. No run read board 22's `forcing?` note on the 9/24
    sheet. Board 1's declarer on the 6/29 sheet is West, which Opus 5 read in 4
    runs of 10, Opus 5.5 in 3, and Sonnet 5.5 in at most 2 at any effort.
  - **Board 17's `2D_H`**, a transfer announced as hearts, on the 6/29 sheet:
    Opus 5 read it in 9 runs of 10, Sonnet 5.5 at `max` in 8, Opus 5.5 in 5, and
    Sonnet 5.5 at `xhigh` and below in none. The usual misreading, `2P_H`, does
    not parse, so review catches it.
  - **Opus 5 against Opus 5.5**: Opus 5 dropped at least one of board 13's alert
    ticks on the 6/29 sheet in every run, read the 9/24 sheet's `diams` note as
    `diam` in every run, and marked board 22's `[3D]` as an opponent's call
    in 3.
  - **Sonnet 5.5's slips at `high`**: beyond the shared misses and board 17, a
    final bid contradicting its own contract (board 13, 2 runs) and `50` for
    `5D` (board 8, 2 runs) on the 6/29 sheet; board 9's circle dropped (3 runs),
    an opponent's call given to our side (board 15, 1 run) and `diams` read as
    `drama` (1 run) on the 9/24 sheet. At `xhigh` and `max`, only board 8's `50`
    recurred, once at each, and `max` once read `diams` as `drains`.
  - **Haiku 5.5's slips**: it read club bids as diamonds, board 10's `(3C)` in
    about half its runs and board 20's in some, and dropped the parentheses that
    mark an opponent's call. About one wrong auction a sheet passed the vote
    unflagged, at every effort.
  - **Speed**: a run's median time was 26 seconds on Opus 5.5, 30 on Sonnet 5.5
    at `xhigh`, and 44 on Opus 5. Haiku 5.5 took from half a minute at `low` to
    four minutes at `max`.

## Effort {#effort}

Supports spec.md #extraction-effort.

- **Sonnet 5.5 and Haiku 5.5 from `low` to `max`** (2026-10-10, from the sweeps
  behind the four-release entry in #model-choice):
  - **Sonnet 5.5**: at `low` and `medium` it wrote about 1,500 output tokens,
    the transcription with next to no thinking. In 4 runs of 10 at each on the
    6/29 sheet, it abandoned the lead notation, writing `Q₀H` or `Q♣` for `QoH`.
    The parser rejects those, so each such run sent most of the sheet's boards
    to review. `xhigh` read about as well as `max` at a quarter of the cost.
    `max` cost \$0.20 a run on the 9/24 sheet and \$0.60 on the 6/29 sheet,
    where single runs took up to 11 minutes and \$0.91.
  - **Haiku 5.5**: effort barely moved its accuracy. Its output grew from about
    9,000 tokens a run at `low` to about 60,000 at `max`, and its time from half
    a minute to four minutes. A run cost about a cent below `max` and three
    cents at `max`.
- **Opus 5.5 at `high` against `medium`** (2026-09-24, the 6/29 sheet, 10 runs
  at each effort over three strip sets): the two efforts read the sheet alike to
  within a cell or two a sweep. On the one ambiguous call that was not noise,
  `high` read the parseable value where `medium` did not. A sheet's two
  transcription runs cost about \$0.34 at `high` and \$0.32 at `medium`, plus
  about \$0.05 for the layout reading that cuts its strips.

## Arithmetic check {#arithmetic-check}

Supports spec.md #extraction-accuracy.

- **The first two real teams sheets** (2026-09-06, as ingested on Opus 5): all
  48 boards reconciled exactly — every level, strain, declarer, penalty and
  trick count.

## Voting {#voting}

Supports spec.md #extraction-voting.

- **Board 1's declarer on the 6/29 sheet** (2026-09-24, Opus 5 and 5.5 at `high`
  and `medium`, over three strip sets): every 4S on the game's travellers was
  declared by West, but most runs read North. On strips cut from a correct
  layout reading, Opus 5.5's two runs split between the two in three pairs of
  four, and the vote flagged each split. On an earlier cutting, whose layout
  reading lost the table's right edge (#image-limits), all 24 runs of both
  releases read North, and the vote had nothing to flag.

## Input format {#input-format}

Supports the input-format bullet in spec.md #extraction.

- **Native-resolution strips against the full sheet** (2026-07-21, the 6/29
  sheet, one run each on Sonnet 5): the full 12MP photo reached the model at
  about 56% linear resolution. Every resolution-class error in the full-sheet
  run — a misread contract digit, dropped announcements, box-against-circle
  swaps on dense rows — vanished when the sheet arrived as native-resolution
  crops, and the crops cost less: \$0.21 against \$0.29.
- **Scanner-app files** (2026-09-03): a scanner app that rectifies and crops
  writes files that are all sheet, and they reach the model at 78–98% linear. A
  whole-page read of one comes close to the strips but never better.

## Image limits {#image-limits}

Supports spec.md #image-limits.

- **What an oversized page cost the layout reading** (2026-09-24, the 6/29
  sheet, six layout readings sent oversized and six sized to fit, on Opus 5 and
  5.5): the page went out 2044 pixels wide, and every coordinate the model
  reported came back about 2% short, pulled toward the top-left corner. Four of
  six readings placed the table's right border at 2497–2505, against a printed
  border at 2553; a 2000/2044 shrink predicts 2498. That gap is past the reach
  of `sheet_geometry`'s search for a border's printed line, so every strip lost
  the table's last 50 pixels. The footer came back high, and two footer strips
  cleared the handwritten date by only 2 pixels. Sized to fit, six readings of
  six put the right border on the printed one, and every footer strip clears the
  date by at least 20 pixels.
- **What fitting costs the strips** (2026-09-24, the 6/29 sheet, Opus 5.5): a
  row strip spans the table's full width, about 2500 pixels on a phone scan, so
  fitting it keeps about 80% of the scan's resolution rather than all of it.
  That cost nothing measurable. Opus 5.5 read fitted and full-width strips cut
  from the same geometry differently in at most one cell of 84, on board 17,
  which flips between identical sweeps anyway. The fitted strips also cost about
  6% fewer input tokens. The comparison may not isolate the lost resolution,
  though: if the CLI was already shrinking the full-width strips, both sets
  reached the model at the same size. Whether the CLI was doing so is not
  settled.

## Which model cuts {#cutter-choice}

Supports the caution in scratch/README.md #cutter-choice: cut a strip set once
and keep it fixed.

- **Three cuttings per model** (2026-09-24, the 6/29 sheet sized to fit, Opus 5
  and 5.5): every cutting found 28 rows and a footer. How far each edge moved
  across a model's three, in pixels, against a 73-pixel row pitch:

  | Edge                      | Opus 5 | Opus 5.5 |
  | ------------------------- | -----: | -------: |
  | Row edges, all four sides |      0 |        0 |
  | Footer left edge          |      0 |        0 |
  | Footer top                |     17 |        3 |
  | Footer bottom             |     39 |       13 |
  | Footer right edge         |    395 |       13 |

  Row edges hold because `sheet_geometry` snaps each one to a printed line. The
  footer is measured against nothing, so its box is the model's reading as
  given, and Opus 5.5 reads it far more steadily. Opus 5's wide right-edge
  figure is one reading that stopped just past the date where the other two ran
  nearly to the table's border; all six footer strips keep the handwriting.
  Cuttings still differ — in the footer, and in row tops by a pixel between the
  two models. These figures hold only for a page sized to fit; #image-limits
  measures what an oversized one did.

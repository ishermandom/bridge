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
  out of use does not by itself retire an entry: Opus 5 against Opus 5.5 stays
  until the `opus` alias moves again and that move is measured.

## Sheets measured {#sheets}

- **The 6/29 sheet**:
  `bridge-private/session_analysis/scoresheets/samples/PXL_20260630_191216837.jpg`,
  a raw phone photo, and the only real sheet among the samples.
- **The 9/24 sheet**:
  `bridge-private/session_analysis/scoresheets/archive/862caf5b70a4-Scanned_20260924-1511.pdf`,
  a scanner app's PDF. Its session record, reconciled and reviewed with the
  user, is the answer key for `scratch/settled_session_comparison.py`.

## Model choice {#model-choice}

Supports the **Model** bullet in spec.md #extraction.

- **Opus 5.5 against Sonnet 5.5** (2026-09-28, the 6/29 and 9/24 sheets, 10 runs
  of each release per sheet, all at `high` effort): Opus 5.5 reads better, and
  Sonnet 5.5 costs about half as much. Sonnet never ran calls together or
  dropped a subscript announcement, and it read every alert tracked in the next
  entry in every run. Judged against the 9/24 sheet's session record, Opus read
  139 of its 140 cells right in every run and Sonnet 136. Across their ten runs,
  Opus misread 10 readings and Sonnet 15; ten of each are board 22's note, which
  no run read right. Every cell on both sheets read the same in all 20 runs
  except the ones below, and on each of them Sonnet slipped at least as often as
  Opus:
  - **Hard cells Opus sometimes reads right**: board 1's declarer on the 6/29
    sheet is West, which Opus read in 3 runs and Sonnet in none. Board 17's
    `2D_H`, a transfer announced as hearts, was read in 5 Opus runs and no
    Sonnet run. The usual misreading, `2P_H`, does not parse, so review catches
    it whichever model makes it.
  - **Slips only Sonnet made**: on the 6/29 sheet, a final bid contradicting its
    own contract (board 13, 2 runs) and `50` for `5D` (board 8, 2 runs); on the
    9/24 sheet, board 9's circle dropped (3 runs) and an opponent's call given
    to our side (board 15, 1 run). In one sweep, both runs dropped board 9's
    circle, so the vote let the miss through without a flag.
  - **Handwritten notes**: every run of both releases read board 22's `forcing?`
    on the 9/24 sheet as `boring`. Nine Sonnet runs and two Opus runs ended it
    with the sheet's `?`, the rest with `!`. One Sonnet run read board 14's
    `diams` as `drama`.
  - **Cost**: a sheet's two transcription runs cost \$0.17 on Sonnet where they
    cost \$0.35 on Opus over the 6/29 sheet, and \$0.16 where they cost \$0.31
    over the 9/24 sheet.
- **Opus 5 against Opus 5.5** (2026-09-24, the 6/29 sheet, 20 runs of each
  release across `high` and `medium` effort and three strip sets): Opus 5.5 read
  both of board 13's alert ticks in every run, where Opus 5 read one of them in
  6 runs of 20 and the other in none. It was steadier on two more alerts as
  well, reading board 3's `[2D!]` and board 11's `4C!` in every run against Opus
  5's 16 and 12. Otherwise the two releases read the sheet alike, down to the
  same misreads of board 1's declarer and board 17's bid letter.

## Effort {#effort}

Supports spec.md #extraction-effort.

- **Opus 5.5 at `high` against `medium`** (2026-09-24, the 6/29 sheet, 10 runs
  at each effort, from the sweeps behind the Opus 5 against Opus 5.5 entry): the
  two efforts read the sheet alike to within a cell or two a sweep. On the one
  ambiguous call that was not noise, `high` read the parseable value where
  `medium` did not. A sheet's two transcription runs cost about \$0.34 at `high`
  and \$0.32 at `medium`, plus about \$0.05 for the layout reading that cuts its
  strips.

## Arithmetic check {#arithmetic-check}

Supports spec.md #extraction-accuracy.

- **The first two real teams sheets** (2026-09-06, as ingested on Opus 5): all
  48 boards reconciled exactly — every level, strain, declarer, penalty and
  trick count.

## Voting {#voting}

Supports spec.md #extraction-voting.

- **Board 1's declarer on the 6/29 sheet** (2026-09-24, Opus 5 and 5.5, from the
  sweeps behind the Opus 5 against Opus 5.5 entry): every 4S on the game's
  travellers was declared by West, but most runs read North. On strips cut from
  a correct layout reading, Opus 5.5's two runs split between the two in three
  pairs of four, and the vote flagged each split. On an earlier cutting, whose
  layout reading lost the table's right edge (#image-limits), all 24 runs of
  both releases read North, and the vote had nothing to flag.

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

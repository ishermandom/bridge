# Harnesses that run against live models and real captures

Neither harness here is a test. Both need something the test suite deliberately
does without — a paid model call, or the private captures on disk — so they are
run by hand when there is a reason to, and what they measure is recorded
wherever the decision it supports lives.

## Extraction model comparison

A harness for re-running the live comparison behind the extraction model choice.
The measurements it produces are recorded in spec.md #extraction — the model
bullet's quality and cost figures — and in spec.md #extraction-voting, which
rests on how consistent the chosen model is with itself.

**Re-run it when `vision_model_invocation.DEFAULT_MODEL` or `DEFAULT_EFFORT`
moves.** Those spec figures are measurements of one setting against one
alternative, so a change to either silently invalidates them; the whole point of
keeping the harness is that refreshing them should take a few commands rather
than a rebuild.

`DEFAULT_MODEL` names an alias rather than a release, so it can also move
without an edit here — the alias follows the family forward whenever the CLI
updates. Each run records the release that answered alongside the alias that was
asked for, so a refreshed figure says which release it describes.

### Running it

Every comparison reads one fixed set of strips. Cutting rests on the sheet's
layout reading, and that reading is a model call whose answer varies: two
cuttings of one image are never byte-identical. So the strips are cut once and
saved, and every sweep after that reads the saved set rather than cutting its
own.

First, `cut` a strip set from a scan and save it.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/strips_model_comparison.py cut \
  --image ../bridge-private/session_analysis/scoresheets/samples/PXL_20260630_191216837.jpg \
  --output-directory /tmp/strips-6-29
```

Then `transcribe` that set at each setting, in one invocation or several. Each
run's raw transcription and its cost and token figures are written as JSON
beside a copy of the strips it read.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/strips_model_comparison.py transcribe \
  --strips-from /tmp/strips-6-29 \
  --output-directory /tmp/strips-comparison \
  --models opus sonnet --efforts high --runs 2
```

Both scripts enforce the fixing. The harness will not cut a new set into a
directory that already holds one, and the scoring step below will not vote runs
that read different sets. `--layout-model` names the model that cuts, defaulting
to `DEFAULT_MODEL`; #cutter-choice says how much that choice matters.

`voted_session_comparison.py` then scores those runs the way the pipeline does —
each model's two runs voted against each other, reporting the issues a review
queue would actually hold.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/voted_session_comparison.py \
  --run-directory /tmp/strips-comparison
```

### Five things to know before trusting the numbers

- **Cost is per sheet, not per run.** A sheet takes two transcription runs for
  the vote, plus the layout reading that cuts its strips, so a per-run figure
  understates what a sheet costs. The second run is barely cheaper than the
  first: only about 2,900 tokens of the prompt are ever served from cache, and
  the strips go out in full every time.
- **One sweep's dollar figures are rough.** Output tokens swing from run to run,
  enough to move an arm's cost by several cents between two sweeps over the same
  strips — Opus 5 at `medium` cost $0.43 in one and $0.39 in the next. Quote an
  arm's cost averaged over sweeps. Cache order matters much less than it looks:
  a cold run costs about a cent more than a warm one, so `cache_read_tokens` is
  worth checking only to rule it out.
- **One sweep is a first look, not a figure.** Even over a fixed strip set, two
  sweeps of one arm read a cell or two differently — on the 6/29 sheet, 0–2
  cells of 84 — so a difference of that size between two arms is noise until a
  second sweep repeats it. Across different cuttings the differences run larger,
  which is why the set stays fixed.
- **Which model cuts matters less than cutting once** {#cutter-choice}. Three
  cuttings of the 6/29 sheet per model all found 28 rows and a footer. How far
  each edge moved across a model's three, in pixels, against a 73-pixel row
  pitch:

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
  two models — so keep a set fixed across sweeps; the default cutter serves.
  These figures hold only for a page sized to fit; spec.md #image-limits
  measures what an oversized one did.

- **Raw-string diffs mislead in both directions.** Some differences vanish in
  parsing (`X` and `*` are the same call) and some spacing differences are fatal
  (`1N2C2D3N` has no seam for the parser to split on). This is why the second
  script exists — judge on its output, not on eyeballed transcriptions.

Real scans carry other club members' names and results, so they live in
`bridge-private` and the output directory belongs outside this repo — see
spec.md #captures-and-pii, which also names the sheet the figures were measured
on.

## Reconciliation against the stored captures

`reconciliation_against_captures.py` runs the traveller join over the records
`traveller_store` has written, rather than over fixtures. It reports each
capture alone and then the two merged, reconciles a sheet synthesized from them,
seeds the board swap the 6/29 sheet actually carried, and finally runs with no
traveller at all.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/reconciliation_against_captures.py \
  --name 'Your Name'
```

**Re-run it when the join or any capture parser changes.** What it is good for
is the thing fixtures cannot show: that two publishers of one real session merge
without losing a field, and that a seeded swap is found without dragging its
neighbours in with it. The faithful pass agrees by construction — the sheet is
built from the traveller — so read it as a floor, not as evidence.

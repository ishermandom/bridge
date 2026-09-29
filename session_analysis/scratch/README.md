# Harnesses that run against live models and real captures

No harness here is a test. Each needs something the test suite deliberately does
without — a paid model call, or the private captures on disk — so each is run by
hand when there is a reason to. Where a harness measures something, the
measurement is recorded in measurements.md, under the decision it supports.

## Extraction model comparison

A harness for re-running the live comparison behind the extraction model choice.
The measurements it produces are recorded in measurements.md, chiefly under
#model-choice, #effort, and #voting.

**Re-run it when `vision_model_invocation.DEFAULT_MODEL` or `DEFAULT_EFFORT`
moves.** Those figures are measurements of one setting against one alternative,
so a change to either silently invalidates them; the whole point of keeping the
harness is that refreshing them should take a few commands rather than a
rebuild.

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

First, `cut` a strip set from a scan and save it. The scan is read the way
ingest reads one, so it can be a photo or a scanner app's PDF, as long as it
holds a single sheet.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/strips_model_comparison.py cut \
  --scan ../bridge-private/session_analysis/scoresheets/samples/PXL_20260630_191216837.jpg \
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

The vote shows how often a model disagrees with itself, not how often it is
right. A settled session — one reconciled against the travellers and reviewed
with the user — has a record in `bridge-private` that serves as an answer key,
and `settled_session_comparison.py` judges every run's every board cell against
it. For each setting, it reports how many cells all of that setting's runs read
right, and how many cell readings across those runs were wrong. It then lists
each cell any run missed, with how many runs read that cell correctly and what
the others read instead. It takes any number of run directories, so every sweep
over one strip set is judged together.

It refuses runs whose strips were cut from a different scan than the one the
session was ingested from. Ingest moves each scan into `scoresheets/archive/`,
so `cut` from that copy. The record itself sits in `sessions/pending/` whether
or not it has been settled.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/settled_session_comparison.py \
  --run-directories /tmp/strips-9-24-sweep-1 /tmp/strips-9-24-sweep-2 \
  --settled-session ../bridge-private/session_analysis/sessions/pending/<session>.json
```

### What to know before trusting the numbers

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
- **Which model cuts matters less than cutting once** {#cutter-choice}. Row
  edges come out the same from every cutting, since `sheet_geometry` snaps each
  one to a printed line, but the footer's box is the model's reading as given
  and shifts between cuttings; measurements.md #cutter-choice has the figures.
  So keep a set fixed across sweeps; the default cutter serves.

- **Raw-string diffs mislead in both directions.** Some differences vanish in
  parsing (`X` and `*` are the same call) and some spacing differences are fatal
  (`1N2C2D3N` has no seam for the parser to split on). This is why both scoring
  scripts compare parsed values — judge on their output, not on eyeballed
  transcriptions.
- **The answer key vouches only for what was checked.** A settled session is the
  pipeline's own reading with review's corrections applied. Reconciliation
  checks contracts, declarers, results, and leads against the travellers, but an
  alert, a circle, or a note is checked only if a reviewer happened to look. On
  those cells the key holds the reading of whichever model ingested the sheet,
  so it leans toward that model and can share its misreadings. The 9/24 sheet's
  board 22 note, `forcing?`, was settled as `boring!`, the reading Opus 5.5 gave
  in 8 runs of 10. Before crediting a model with such a cell, confirm the answer
  with the user. Having Claude view the crop is no substitute: checking this
  one, it read `boring!` too. And when every run reads a cell the same way and
  the key disagrees, the ink itself may be wrong: a sheet error corrected in
  review, which every run read faithfully.

Real scans carry other club members' names and results, so they live in
`bridge-private` and the output directory belongs outside this repo — see
spec.md #captures-and-pii. measurements.md #sheets names the sheets the figures
were measured on.

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

## Fixture analysis solved from its deals

`published_analysis.py` writes the analysis each traveller fixture publishes:
its double-dummy table, its par, and its opening-lead notes. It derives all
three from the fixture's own deals and writes them in that capture format's
notation; travellers.md `#fixture-analysis` says why.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/published_analysis.py check
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/published_analysis.py rewrite
```

**Run `check` before trusting `rewrite`.** No source documents its notation, so
every rule the generator follows was inferred from real captures: the order of a
table's cells, its spacing, when two seats are written apart, which leads a note
names. `check` regenerates the analysis of every capture in the private tree and
reports each place it differs from what the source published. Re-run it as
captures accumulate: one unlike any seen so far can break a rule that nothing on
hand has exercised.

**Re-run `rewrite` when a fixture's deal changes.** A new fixture first needs an
entry in the script's table of fixtures, which names each fixture's format. The
rewrite touches the analysis alone and leaves every other byte as it was.

# Extraction model comparison

A two-step harness for re-running the live comparison behind the extraction
model choice. The measurements it produces are recorded in spec.md #extraction —
the model bullet's quality and cost figures — and in spec.md #extraction-voting,
which rests on how consistent the chosen model is with itself.

**Re-run it when `vision_model_invocation.DEFAULT_MODEL` moves.** Those spec
figures are measurements of one specific model against one specific alternative,
so a model bump silently invalidates them; the whole point of keeping the
harness is that refreshing them should be a two-command job rather than a
rebuild.

## Running it

`strips_model_comparison.py` cuts one scan's strips once and has each model read
those same strips, so the model is the only variable. It writes each run's raw
transcription and its cost and token figures as JSON.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/strips_model_comparison.py \
  --image ../bridge-private/scoresheets/PXL_20260630_191216837.jpg \
  --output-directory /tmp/strips-comparison \
  --models claude-opus-5 claude-sonnet-5 --runs 2
```

`voted_session_comparison.py` then scores those runs the way the pipeline does —
each model's two runs voted against each other, reporting the issues a review
queue would actually hold.

```sh
PYTHONPATH=. uv run --project . python \
  session_analysis/scratch/voted_session_comparison.py \
  --run-directory /tmp/strips-comparison
```

## Two things to know before trusting the numbers

- **Cost is per sheet, not per run.** The second run of a pair reads the prompt
  cache the first one filled and costs about half as much, so a per-run figure
  means nothing unless it says which run it describes. Re-running the same
  strips inside the cache window measures a warm run, not a fresh one.
- **Raw-string diffs mislead in both directions.** Some differences vanish in
  parsing (`X` and `*` are the same call) and some spacing differences are fatal
  (`1N2C2D3N` has no seam for the parser to split on). This is why the second
  script exists — judge on its output, not on eyeballed transcriptions.

Real scans carry other club members' names and results, so they live in
`bridge-private` and the output directory belongs outside this repo — see
spec.md #captures-and-pii, which also names the sheet the figures were measured
on.

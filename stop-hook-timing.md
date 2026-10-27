# Where the Stop hook's time goes

A measurement of the Stop hook's run over this repo, taken on 2026-10-27 on
Python 3.15, with every millisecond attributed where it could be. The hook
itself lives in the dotfiles repo (`claude/hooks/stop_checks.sh`); this repo
supplies `run_tests.sh` and the code the hook checks. The figures are a snapshot
of that day's code and machine, so treat them as proportions to re-measure
rather than as current values. `scratch/stop_hook_timing/measure.sh` re-runs
every timing below.

## How it was measured

- **A quiet machine**: every timing ran while the machine's load average stayed
  between 1.9 and 3.9 on 10 cores. A run taken during another session's browser
  tests, at a load near 30, came out two to three times slower.
- **Interleaved rounds**: 16 rounds, each running the hook untraced, the hook
  traced, and the hook's pytest invocation alone, so drift over time touches
  every variant alike. Untraced runs took 3,391–3,514ms.
- **Tracing**: bash's command trace timestamped every command in every script
  the hook runs, and a pytest plugin timestamped pytest's phases. The gaps
  between consecutive events split each run into back-to-back segments, each
  charged to the command or phase that began it, so the rows add up exactly to
  the run's total. Tracing added 42ms.
- **Means, not medians**: means add up, so the rows below sum to the totals.
- **Quiet rounds only**: a round more than 5% slower than the fastest is left
  out whole, as other load most likely slowed it. Two traced rounds were.
- **Breaking rows down further**: separate timings of each tool alone (10
  rounds), of pytest's internals (8 rounds), and of candidate levers (8 to 16
  rounds), plus an import-time log and a sampling profile of collection.
- **The JavaScript checks' priority**: these hook runs started the userscript's
  checks under macOS's `taskpolicy -c utility`, which was tried and then set
  aside (see #set-aside). They slowed pytest by about 61ms here; at normal
  priority, the run before measured about 91ms.

## The whole hook

Means of the traced runs; untraced runs average 3,426ms.

| Step                                                              |    ms |
| ----------------------------------------------------------------- | ----: |
| Tests (`run_tests.sh`)                                            | 2,067 |
| Formatting (`format.sh`: one pass over bridge, one over dotfiles) | 1,082 |
| mypy (`mypy-check.sh`)                                            |   232 |
| Lint report (`ruff-lint.sh`)                                      |    41 |
| Third-party check (`is-third-party-repo.sh`)                      |    35 |
| Launching the hook, its own lines, and its exit                   |    12 |
| **Total**                                                         | 3,468 |

## Tests: 2,067ms

| Part                                                                 |    ms |
| -------------------------------------------------------------------- | ----: |
| Startup: uv's overhead                                               |  18.6 |
| Startup: the Python interpreter                                      |  13.5 |
| Startup: importing pytest (287 modules)                              |  62.7 |
| Startup: pytest before loading plugins (not split)                   |   1.6 |
| Plugin setup (the repo has no conftest files)                        |   3.4 |
| Configure: standard-library imports                                  |   6.0 |
| Configure: other                                                     |   1.9 |
| Collection: third-party imports                                      |  ~159 |
| Collection: project imports                                          |   ~66 |
| Collection: standard-library imports                                 |   ~39 |
| Collection: everything besides imports (see #collection)             |   134 |
| Collection: slowdown from the JavaScript checks running alongside    |    26 |
| Test loop: the tests' own setup, call and teardown                   | 1,181 |
| Test loop: pytest's work around each of the 1,320 tests (~90µs each) |   119 |
| Test loop: outside any test                                          |    16 |
| Session end: mostly deleting earlier runs' temporary directories     |    50 |
| Cleanup: pytest's forced garbage collection                          |    36 |
| Other small gaps between pytest's phases                             |   1.1 |
| Python's shutdown                                                    |   ~78 |
| Process exit, then uv's exit                                         |   ~12 |
| Bash scripts, `git`, `mktemp`, `cat` and `rm` around pytest          |    43 |

- **Collection's third-party imports**: pypdf 20ms, soupsieve 16, endplay 15,
  pydantic 15, Pillow 13, playwright 11, charset_normalizer 11, markdown_it 9,
  pydantic_core 9 and reportlab 8, with about 33ms across the rest. The project
  imports are mostly `session_analysis` (33ms) and `system_notes` (21ms).
- **The tests' own time, by file**: `ingest_test` 180ms, `traveller_store_test`
  167, `render_card_test` 125, `sheet_geometry_test` 95, `filters_test` 67,
  `sheet_structure_test` 64, `scan_decoding_test` 61, five more files at 26–45ms
  each, and the other 48 files 239ms in all.
- **The JavaScript checks** (tsc ~270ms, then vitest ~680ms) run in the
  background and finish about a second before pytest, so the hook never waits on
  them directly. They cost about 61ms by competing with pytest for the CPU, and
  the pytest rows already include that cost: 26ms in collection, 32ms in the
  test loop, and 3ms elsewhere.

## Formatting: 1,082ms

| Part                                                                         |  Bridge | Dotfiles |
| ---------------------------------------------------------------------------- | ------: | -------: |
| prettier `--write`                                                           |     187 |      234 |
| … of which Node and prettier startup                                         |     ~97 |      ~97 |
| … of which expanding the `**/*` patterns                                     |     ~48 |      ~82 |
| … of which checking cached files (bridge 36, dotfiles 51; none changed)      |     ~40 |      ~51 |
| prettier `--find-config-path`: a second launch, to look for a project config |     100 |       98 |
| `find` probe for `*.ts`                                                      |      25 |      194 |
| `find` probes for `*.js` and `*.md`                                          |      13 |        7 |
| `quiet-prettier.sh`'s other lines                                            |      13 |       13 |
| `ruff check --fix`: ruff itself, then uv's overhead                          | 11 + 18 |   9 + 13 |
| `ruff format`: ruff itself, then uv's overhead                               | 11 + 18 |  10 + 12 |
| `quiet-ruff.sh`'s other lines (bash, `git`, `find`)                          |      20 |       20 |
| **Pass total**                                                               |     414 |      610 |

`format.sh`'s own lines add 24ms, and its third-party check 34ms.

- **The dotfiles `*.ts` probe** walks that checkout's git-ignored `.claude/`
  folder, which holds other sessions' worktrees (42,681 entries at the time),
  and finds nothing. Skipping that folder brings it to 24ms.
- **Prettier's pattern expansion** also walks ignored folders before applying
  its ignore rules: handed the same files as an explicit list, the write pass
  runs 48ms faster in bridge and 82ms faster in dotfiles.

## mypy, lint, and the third-party check

- **mypy, 232ms**: uv's overhead ~20ms; mypy's startup ~81ms; loading its cached
  results for about 2,000 modules and finding none changed ~103ms; the bash,
  `git` and `find` calls around it 27ms.
- **Lint, 41ms**: ruff itself 10ms and uv's overhead 19ms; the bash and `git`
  calls around them 12ms.
- **Third-party check, 35ms, run twice per hook with the same answer**: three
  `git` calls 13ms; six `dirname` calls while it walks up looking for a
  `.gclient` file 8ms; bash startup 6ms; its other lines 8ms.

## Costs that recur across steps

- **uv's overhead**: about 119ms over 7 `uv run` calls — roughly 18ms each in
  bridge and 12ms in dotfiles.
- **Prettier launches**: about 390ms of Node and prettier startup, across 4
  launches.
- **Bash script launches**: about 81ms across 14 scripts, roughly 5.8ms each.
- **`git` calls**: 67ms across 15 calls from the hook's scripts, plus one inside
  pytest.

## Why collection is slow {#collection}

Collection imports every test module and everything those modules import — 665
modules — and Python runs each module's top-level code as it loads. With pytest
alone it takes about 400ms. A sampling profile splits it as follows; the sampler
itself slows collection by about 6%:

- **Imports, ~250ms**: modules the tests exercise. `double_dummy_solving` defers
  the imports endplay's own modules make, so the plotting stack endplay's deal
  generator imports (matplotlib, numpy, pyparsing and tqdm) never loads.
- **pytest's own work, ~110ms**: collecting captured output after each directory
  and file it collects (16ms), inspecting test functions' signatures (11ms),
  path handling and directory walking (~17ms), and many small costs.
- **Test modules' own top-level code, ~37ms**: almost all in
  `render_card_test.py`, which reads and parses the base card PDF and registers
  fonts at import. Its tests need that work, so moving it would only shift it
  into the test loop.
- **Loading test modules, ~18ms**: finding them and reading the bytecode pytest
  caches for its rewritten assertions.
- **`git`, ~6ms**: the one lookup of the private checkout, made when
  `render_card_test.py` reads the base card.
- **Garbage collection, ~36ms (40ms in the hook)**: spread across the above, as
  imports allocate many objects. The same objects are scanned again by pytest's
  forced collection at cleanup and during Python's shutdown.

## Freezing what collection loads {#freeze-variants}

Garbage collection could be paused while pytest collects, and everything alive
at that point then frozen with `gc.freeze()`, so that later collections never
scan it again. Collection leaves about 138,000 objects alive for the whole run.
Without a freeze, pytest's two forced garbage collections at session end and
Python's shutdown rescan them all; frozen, they are never scanned again, and the
end of the run falls from ~185ms to ~84ms. pytest alone, 8 interleaved rounds:

| Variant                                                           |   pytest's run | Peak memory |
| ----------------------------------------------------------------- | -------------: | ----------: |
| As the hook runs it                                               |        1,983ms |      452MiB |
| Pause garbage collection while pytest collects, then freeze       | 1,861ms (−122) |      +12MiB |
| The same, with one full garbage collection just before the freeze | 1,882ms (−101) |       +5MiB |

- **Trapped garbage**: while garbage collection is paused, about 50,000 garbage
  objects pile up, and a freeze straight after collection keeps them for the
  rest of the run. One full collection before the freeze clears them first, at a
  cost of ~24ms. Peak memory varies by a few MiB from run to run; across two
  runs, freezing straight away cost 5–7MiB more than freezing after the full
  collection.

Both variants share three tradeoffs:

- **A gap in pytest's finalizer check**: pytest's end-of-session collections
  exist to run pending finalizers and report exceptions raised inside them. A
  frozen object is never examined again, so when a test drops the last reference
  to an import-time object caught in a reference cycle, its finalizer never runs
  and any error in it goes unreported. Objects the tests create are checked as
  before.
- **A difference from production**: tests would collect garbage differently from
  the Streamlit app and the command-line tools, so code whose behavior depends
  on when garbage is collected — a weak-reference cache, cleanup in a finalizer
  — could pass its tests and misbehave in production.
- **A repo-wide `conftest.py`**: the lever would add the repo's first
  `conftest.py`, at the root, which would apply to every pytest run in the repo,
  not only the hook's.

As of 2026-10-27 the project defines no finalizers and uses no weak references,
so neither the finalizer gap nor the difference from production touches its own
code.

## Levers set aside {#set-aside}

- **Ending the process with `os._exit` after pytest's last cleanup**: it would
  save most of Python's shutdown, about 87ms with pytest alone. But it skips
  every exit handler and finalizer still pending, and the exit status would have
  to be passed on by hand, where a slip makes a failing run look like a pass.
- **pytest's cleanup of temporary directories (~50ms)**: pytest keeps the last
  three runs' temporary directories, so each run deletes the oldest run's. Its
  retention settings only change which run's directories are deleted, or when.
  Writing fewer files is the one thing that shrinks it, which
  [tasks.md](tasks.md#fake-filesystem) #fake-filesystem would do.
- **The JavaScript checks at a lower priority**: under `taskpolicy -c utility`,
  pytest ran 42–45ms faster beside them in three batches, but 11ms slower in a
  fourth of 16 rounds. The lower classes, `-c background` and `-b`, slow the
  checks to about 4s, so the hook would wait on them, and `nice -n 20` makes no
  measurable difference.
- **vitest on a single worker**: it eased the contention by 35–50ms in one
  batch, but the checks then take about 1.9s and finish only ~0.15s before
  pytest, so any speedup to pytest would leave the hook waiting on them.
- **Leaving out the two test files whose every test the hook deselects**: no
  saving, since other test files import the same modules.

## What isn't attributed

- **Tracing itself, 42ms**: the tables describe traced runs; untraced runs are
  42ms faster, and the difference is not apportioned among the rows.
- **Collection's work besides imports, 134ms**: split above only by sampling,
  which slightly perturbs it.
- **mypy's cache check, ~103ms**, and **Python's shutdown, ~78ms**: measured as
  wholes. Shutdown was measured by ending the process with `os._exit` before
  shutdown runs. The inference that garbage collection dominates shutdown rests
  on how much a freeze shortens the end of the run.
- **The configure step's imports, 6ms**: `readline` comes from pytest's output
  capture; the rest (email, urllib, ipaddress) was not traced to its importer.
- **Small leftovers, about 10ms**, spread across a few rows; the sub-splits come
  from separate timings, so they miss their row's total by up to 4ms.
- **Claude Code's own share**: launching the hook command and reading its result
  happen outside anything the hook can time.
- **Run-to-run noise**: untraced runs spanned 123ms.

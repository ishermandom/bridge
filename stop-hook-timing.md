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
- **Rotating the order** (added 2026-11-03): a variant that leaves work behind
  slows whichever runs next. Run right after pytest-rs on 4 workers, whose
  temporary directories the next pytest deletes, plain pytest measured ~120ms
  slower. Later batches rotate the order each round.
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

## Formatting: 1,082ms {#formatting}

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

### Prettier's launches {#prettier-launches}

Measured on 2026-11-01. The dotfiles branch `worktree-formatting-step` (at
`16b8108`) hands prettier the files `git ls-files` lists, which removes both
walks above and takes the step from ~1,045ms to ~693ms. Most of what remains is
prettier starting up: four launches a Stop, a config check and a formatting run
per repo, at ~99ms each under Homebrew's Node.

- **Why a launch costs ~99ms**: Homebrew's `node` spends ~73ms before its
  JavaScript engine starts, as `node --version` shows. It links 99 shared
  libraries, 93 of them Homebrew's and 72 of those abseil's, because Homebrew's
  formula builds Node as a shared library and swaps every bundled dependency for
  the Homebrew formula of it. That follows Homebrew policy, and no option
  changes it. The official nodejs.org build links four system libraries and
  starts in ~18ms. Prettier's own code adds ~15ms.
- **Bun 1.4.4** formats byte for byte as Node does: 1,106 files, from the user's
  repos plus a sample of third-party ones, under four option sets.
  `quiet-prettier-test.sh` passes with prettier under Bun. Prettier's cache key
  includes the Node version the runtime reports, so every launch sharing a cache
  must use the same runtime.
- **Prettier's experimental command line** (`--experimental-cli`) checks the
  same files in ~24ms under Bun. But it exits 1, not 2, on a parse error or a
  missing file, which `format.sh` reads as a finding rather than breakage, and
  it has no `--find-config-path`.

| One prettier launch | `--version` | `--check`, 39 cached files |
| ------------------- | ----------: | -------------------------: |
| Homebrew Node       |        99ms |                      143ms |
| Official Node       |        39ms |                       85ms |
| Bun                 |        25ms |                       62ms |

Replacement formatters, against prettier 3.9.10 at the house settings. The
corpus is the same 1,106 files; the user's own Markdown is 111 of them.

| Tool                    | User's Markdown that differs | Whole corpus | One repo's pass |
| ----------------------- | ---------------------------: | -----------: | --------------: |
| oxfmt 0.75              |                     3 of 111 |        0.07s |            ~8ms |
| Biome 2.6.4             |                    61 of 111 |        0.20s |         29–70ms |
| dprint, its own plugins |                    44 of 111 |         2.1s |                 |
| dprint, prettier plugin |                     5 of 111 |         8.0s |                 |

- **oxfmt** is built against prettier 3.9.10 and documents each divergence. Its
  three differing files differ only in where a line breaks. Its standalone
  binary reads no stdin, which `reflow_prose.py` relies on.
- **The dprint plugin** bundles prettier 3.8.4, whose Markdown parser reads the
  underscores in `a_b_c` as emphasis and rewrites them as asterisks.

The whole step, median of 12 interleaved rounds:

| Setup                                   | Formatting |
| --------------------------------------- | ---------: |
| `main`                                  |    1,045ms |
| The file list                           |      693ms |
| The file list, prettier under Bun       |      393ms |
| oxfmt in prettier's place, only checked |      222ms |

The config check answers "no project config" in every repo the hook formats. The
one repo of the user's with a prettier config of its own, google-photos-deduper,
also loads an import-sorting plugin that no replacement runs, and the hook skips
it as third-party.

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

## The Rust tests' step {#cargo-step}

Measured on 2026-11-01 on `main`, with `cargo test` run alone over a copy of the
crate unless a figure says otherwise. `run_tests.sh` runs the step as its own
background job beside pytest.

- **Warm, about 400ms**: the brute-force tests the crate does not `#[ignore]`
  take ~210ms, a doc-test pass over a crate with no doc examples ~47ms, cargo's
  up-to-date check ~24ms, and the other test programs with their launches the
  rest.
- **Over the 25ms per-test budget**, each run alone: all six brute-force tests
  the crate runs by default, from `a_finesse_against_two_honors_agrees` (241ms)
  down to `a_simple_finesse_agrees` (38ms), and
  `lines::aq76_opposite_t853_for_2_reaches_its_target` (43ms). Skipping the
  seven halves the step, from ~406ms to ~195ms.
- **After an edit**: the tests build at `opt-level = 3`, so touching a source
  file makes the step 2.35–2.55s and touching a test file ~0.68s. A new
  worktree's first build takes ~6.2s.

Where the step runs, as the whole hook's median over 12 interleaved rounds:

| Runner                            | Warm    | After touching `src/describe.rs` |
| --------------------------------- | ------- | -------------------------------- |
| No Rust step at all               | 3,417ms | 3,467ms                          |
| Cargo first                       | 3,820ms | 5,993ms                          |
| Cargo as its own background job   | 3,470ms | 4,178ms                          |
| Own job, skipping the seven tests | 3,462ms | 4,206ms                          |

An earlier batch, on the branch the crate landed from, also timed cargo leading
the JavaScript chain: +46ms warm against no Rust step, and +1,286ms after an
edit, where its own job measured +426ms in the same batch. Leading that chain,
the rebuild and the ~1s of JavaScript checks run in series and outlast pytest;
as its own job, the rebuild overlaps them.

Once cargo runs in the background, skipping the seven tests saves nothing on
either kind of turn, so the hook runs them all. After an edit, what the
background job still costs is most likely the rebuild competing with pytest for
the processor rather than cargo outlasting it, since a shorter test run does not
shorten it.

Skipping the doc-test pass (`doctest = false`) was set aside: it saves ~47ms,
and a doc example added later would silently never run.

## The concurrent Stop chain {#concurrent-chain}

Measured 2026-11-02 to 2026-11-03, over a bridge worktree. The dotfiles branch
`worktree-formatting-step`, now on `main`, hands prettier the files git lists,
runs it under Bun, makes the third-party check cheaper, and runs in parallel
whatever cannot collide: the two formatting passes, prettier beside ruff within
each, and mypy, the tests and lint, with the third-party checks overlapping work
that does not wait on them. The whole Stop, medians of 12 interleaved rounds:

| Chain                                   | Whole Stop |
| --------------------------------------- | ---------: |
| Installed (prettier on Homebrew's Node) |    3,426ms |
| File list and Bun, steps one at a time  |    2,824ms |
| The branch, with everything concurrent  |    2,352ms |

The rows come from batches at load averages of 4 to 6, so they compare within a
batch rather than across batches. Where the concurrent chain's time goes,
milliseconds from the hook's launch, medians of 8 runs of a timestamped copy:

| Span                                                      |  From |    To |
| --------------------------------------------------------- | ----: | ----: |
| Formatting, both passes in parallel; prettier ~130ms each |     9 |   213 |
| mypy, beside the tests                                    |   249 |   555 |
| lint, beside the tests                                    |   255 |   296 |
| The tests, from `run_tests.sh` starting                   |   252 | 2,346 |
| … pytest's plugins loaded                                 |   407 |       |
| … collection, 477ms                                       |   425 |   902 |
| … the test loop, 1,240ms                                  |   902 | 2,142 |
| … pytest's last exit hook, then shutdown and uv's exit    | 2,237 | 2,346 |

In that copy the third-party checks still ran in series, ~33ms each, which the
branch now overlaps.

## What competes with pytest {#contention}

Measured on 2026-11-03. In the dotfiles Stop chain, mypy and lint run beside
`run_tests.sh`, whose cargo tests and JavaScript checks run beside pytest. With
each started the moment pytest starts, pytest's whole run against running alone,
medians of 8 interleaved rounds:

| Beside pytest                   |   Slowdown |
| ------------------------------- | ---------: |
| mypy                            |      +17ms |
| lint                            |       −1ms |
| cargo's tests                   |      +18ms |
| the JavaScript checks           |      +82ms |
| mypy and lint                   |      +15ms |
| cargo and the JavaScript checks |     +168ms |
| all four                        | +195–213ms |

The two that compound both spread across many cores: cargo runs its tests in
parallel threads, and vitest in parallel workers after `tsc`.

Arranging the four differently, the step ending with whichever arm finishes
last:

- **One arm in series, mypy and lint, then the JavaScript checks, then cargo**:
  ~60ms faster warm, but ~1s slower after an edit to the crate, since cargo's
  ~2.4s rebuild then waits its turn and the arm outlasts pytest.
- **cargo capped at 2 test threads**: 62ms faster in one batch of 8 rounds, but
  11ms in a second of 16, so within noise, and no slower after an edit. With no
  gain to show, the cap was left out.

## Performance and efficiency cores {#core-kinds}

Measured on 2026-11-03. This machine has 4 performance cores and 6 efficiency
cores. macOS has no command to pin a process to a core, only scheduling classes:
`taskpolicy -c background` clamps a process and its children to the background
class, which runs only on the efficiency cores, and slowly. A fixed
single-threaded loop took ~2,000ms there against ~600ms at the default class.
The utility class ran it at full speed, so it confines nothing.

Moving jobs beside pytest into the background class, the step ending with
whichever job finishes last, medians of 8 rotated rounds:

| Moved to the efficiency cores     |    Warm | After touching `src/describe.rs` |
| --------------------------------- | ------: | -------------------------------: |
| Nothing                           | 2,090ms |                          3,050ms |
| The JavaScript checks             | 2,502ms |                          4,146ms |
| cargo                             | 2,017ms |                          4,679ms |
| The JavaScript checks and cargo   | 2,586ms |                          4,992ms |
| mypy and lint                     | 2,063ms |                          2,984ms |
| cargo's test run, after its build | 2,048ms |                          4,685ms |

The last row comes from a second batch, whose own "nothing" row read 2,134ms
warm and 3,865ms after the touch. The batches after the touch ran at load
averages of 13 to 15, partly the rebuilds themselves, so those columns compare
within a batch only.

- **The JavaScript checks** take ~2.5s on the efficiency cores and outlast
  pytest.
- **cargo** frees pytest most: after an edit pytest ran 656ms faster, so cargo's
  rebuild is what competes with pytest then. But the rebuild itself moves to the
  slow cores, and the step ends ~1.6s later.
- **cargo's test run alone**, with the build left at the default class, keeps
  the warm gain: 86ms, where moving all of cargo saved 73ms in both batches.
  After an edit cargo is the last job to finish, so its slower test run still
  adds ~0.8s.
- **mypy and lint** are short enough that moving them gains within noise.
- **vitest on one worker**, at the default class, came out within noise on both
  kinds of turn.

With no arrangement winning on both kinds of turn, the hook keeps running
everything in parallel.

## pytest-rs, a faster runner to revisit {#pytest-rs}

Measured on 2026-11-03 with pytest-rs 0.0.12, an alpha that reimplements
pytest's machinery in Rust and runs the tests on an embedded CPython. On the
hook's selection it reports exactly what pytest does, 1,359 passed and 31
deselected. Medians of 12 rounds, the order rotated each round:

| Runner               | Run alone | Whole Stop, concurrent chain |
| -------------------- | --------: | ---------------------------: |
| pytest               |   1,853ms |                      2,375ms |
| pytest-rs            |   1,655ms |                      2,158ms |
| pytest-rs, 4 workers |   1,050ms |                      1,808ms |

pytest runs alone here as a direct call, without `uv run`. In the chain, four
workers compete with cargo, the JavaScript checks and mypy for cores, which
takes back about a third of what they save alone. pytest-rs's workers do not
each repeat the imports, as pytest-xdist's do.

Adopting it would take:

- **A source build**: it publishes no prebuilt package for Python 3.15, so it
  built with Rust, in about 50 seconds per install or update.
- **Replacing pytest everywhere**: it installs an importable `pytest` package,
  which reports itself as pytest 9.0.3, and cannot share an environment with
  real pytest. Every run would use it, mid-turn and by hand as well as the
  hook's.
- **Unsetting `VIRTUAL_ENV`** for the hook's call: pytest-rs honors it where
  `uv run` ignores it, and the session's points at an unrelated Python 3.14
  environment, where 40 test files then fail to import.
- **Accepting a bundled pytest-benchmark plugin**, which it loads even with
  plugin autoloading off.

## A fresh worktree's first Stop {#fresh-worktree}

Each worktree builds its own caches, so its first Stop pays for all of them: on
the suit-combination-analyzer branch, 25.5s against 4.3s for the next Stop. One
cold run against one warm run, by command:

| What                                                   | Extra on the cold run |
| ------------------------------------------------------ | --------------------- |
| mypy, with no cache yet                                | +8.8s                 |
| Cargo, building the crate and its dependencies         | +6.3s                 |
| pytest's first imports, most likely compiling bytecode | +2.7s                 |
| The first `uv run`, most likely creating `.venv`       | +2.2s                 |
| `npm ci`                                               | +0.7s                 |
| prettier, with an empty cache                          | +0.5s                 |

Entering a worktree now prewarms the checks (dotfiles `claude/docs/design.md`
#prewarm). On main without the Rust step, the prewarm took ~17s, and the first
Stop after it 4.4s against 3.5s fully warm. The remaining ~0.9s was prettier's
cache and a cold `find *.ts` in the formatting step. Since the formatting step
hands prettier the files git lists, only prettier's cache remained: over a fresh
worktree of bridge `main`, medians of 10 rounds on 2026-11-05, the step took
~850ms with prettier's cache empty against ~280ms warm. An empty ruff cache
added nothing, since ruff runs beside prettier and finishes first.

The prewarm now fills prettier's cache too, with a check that rewrites nothing
(dotfiles `claude/hooks/prewarm_checks.sh`). Over a fresh worktree of bridge
`main`, medians of 9 rounds on 2026-11-05, the formatting step took ~271ms after
that check, against ~854ms with prettier's cache empty and ~267ms fully warm.

## The same hook over the dotfiles repo {#dotfiles-repo}

Measured on 2026-11-03 over a clean worktree of dotfiles `main`, as a session in
that repo runs the hook: one formatting pass, and the dotfiles suite as the
tests. The whole Stop, medians of 6 rotated rounds, with the shell tests and
with the test step told to run pytest alone:

| Chain                                       | Whole Stop | Without the shell tests |
| ------------------------------------------- | ---------: | ----------------------: |
| Installed (prettier on Homebrew's Node)     |   18,340ms |                 2,514ms |
| The dotfiles branch, everything in parallel |   17,873ms |                 2,081ms |

Each step alone, medians of 4 rounds: formatting 160ms, mypy 134ms, lint 34ms,
the third-party check 13ms, and the tests 17,853ms. The dotfiles `run_tests.sh`
runs its 12 shell tests one after another, 15,897ms together, then pytest,
1,857ms. The slowest shell tests:

| Shell test                       |   Alone |
| -------------------------------- | ------: |
| `quiet-prettier-test.sh`         | 3,280ms |
| `stop_checks-test.sh`            | 2,916ms |
| `format-test.sh`                 | 2,798ms |
| `worktree-test.sh`               | 1,813ms |
| `python-stdlib-bytecode-test.sh` | 1,263ms |
| `prewarm_checks-test.sh`         |   987ms |
| The other six together           | 2,840ms |

Each shell test builds its fixtures under a temporary directory of its own, so
they can run together. All 12 in parallel took 3,789ms, and 3,945ms beside
pytest, medians of 6 rotated rounds, every test passing.

Without the shell tests, the same chain takes 1,140ms over the dotfiles branch's
own tree, against 2,074ms over `main`, in one batch of 6 rounds. The branch's
`reflow_prose.py` runs prettier under Bun, and on `main` the suite's ten tests
that run real prettier took ~107ms each, where under Bun they take ~36ms. Over
the branch's tree, the test step's ~940ms breaks down as:

- **Start-up, ~130ms**: the runner scripts, `uv run` (~11ms), Python, importing
  pytest (~60ms), and its configuration.
- **Collection, 24ms.**
- **The ten real-prettier tests, ~360ms**: half the test loop.
- **Three tests that run the hook end to end, ~167ms.**
- **One `gate_git_test.py` case, 44ms**: the first deny-list entry, most likely
  paying for bashlex's deferred import on behalf of the whole file.
- **The other 346 tests, ~180ms together**, ~50ms of it a few tests that ask the
  real ruff for a project's line width.
- **Shutdown, ~42ms.**

The suite under other runners, over the branch's tree, medians of 8 rotated
rounds, every runner passing the same 360 tests. "Suite alone" calls each runner
directly; the whole Stop has the runner in the test step, also called directly,
except in the installed row:

| Runner                                      | Suite alone | Whole Stop, no shell tests |
| ------------------------------------------- | ----------: | -------------------------: |
| pytest, through `run_tests.sh` and `uv run` |             |                    1,157ms |
| pytest                                      |       918ms |                    1,112ms |
| pytest-xdist, 2 workers                     |       819ms |                            |
| pytest-xdist, 4 workers                     |       779ms |                    1,012ms |
| pytest-rs                                   |       866ms |                    1,077ms |
| pytest-rs, 2 workers                        |       711ms |                            |
| pytest-rs, 4 workers                        |       592ms |                      806ms |

pytest-xdist helps here because this suite spends its time waiting on prettier
rather than importing, so the imports each worker repeats cost less than the
waits they overlap.

Since dotfiles `036bf09`, the hook's run leaves out the shell tests, and every
Python test that costs 25ms or more. Measured on that change's branch, that
takes a Stop from 18,730ms to 1,104ms on the installed chain, and to 650ms with
the formatting branch's chain, medians of 8 rotated rounds.

Each test was charged its own time plus a share of the costs it shares with
other tests. Its own time was its wall time less any cache misses it paid, as
the cheaper of its medians over 8 runs in the usual order and 8 reversed. A
plugin wrapping each `functools.cache` function found one shared cost, bashlex's
deferred import, at 44ms a run over 157 `gate_git_test.py` tests, 0.28ms each;
with it taken out, no test's cost differed between the orders by more than ~2ms.
The 13 over 25ms, the same on `main` and under Bun, are all in
`reflow_prose_test.py`: the ten that run real prettier and three that run the
hook end to end. Four more sit between the 10ms target and the cutoff, at
10–14ms: three that ask the real ruff for a line width, and one that reads a
file with CRLF line endings.

## Speedups considered and rejected {#set-aside}

- **Dropping prettier's config check**: it costs two prettier launches a Stop,
  ~55ms under Bun. The user kept it to avoid a hard-to-diagnose correctness
  issue, over relying on the global config or remembering its answer per
  directory.
- **oxfmt in prettier's place**: ~170ms less a Stop, at the cost of a formatter
  outside Homebrew. Adopting it would cover `reflow_prose.py` too, which hands
  prettier its text on stdin; oxfmt's standalone binary reads no stdin, so
  `reflow_prose.py` would need another way in (#prettier-launches). ruff,
  through `uv run`, would then be the slower half of each formatting pass. The
  user judged formatting at ~200ms a Stop fast enough.
- **Caching the third-party verdict**: the cheaper check leaves only ~5ms for a
  cache to save. A cached verdict could also go stale when a checkout's remotes
  change, and then either rewrite someone else's checkout or silently skip the
  checks in the user's own.
- **Calling tools from `.venv/bin` rather than through `uv run`**: skipping uv's
  ~10–20ms a call saved nothing once the checks ran in parallel.
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
  fourth of 16 rounds. The background class confines them to the efficiency
  cores, where they outlast pytest (#core-kinds), and `nice -n 20` makes no
  measurable difference.
- **vitest on a single worker**: it eased the contention by 35–50ms in one
  batch, but the checks then take about 1.9s and finish only ~0.15s before
  pytest, so any speedup to pytest would leave the hook waiting on them.
- **Leaving out the two test files whose every test the hook deselects**: no
  saving, since other test files import the same modules.
- **Python 3.15's lazy imports** (measured 2026-11-03): making every import lazy
  with `-X lazy_imports=all` breaks pytest's own import hook, and reportlab's
  fallback imports. Narrowed by an import filter to the imports the project's
  own code makes, every selected test still passes, but collection takes as long
  as before: the tests the hook runs use every heavy library they import, so
  deferring an import only moves its cost into the test loop.
- **Switching off pytest's unused built-in plugins** (measured 2026-11-03), such
  as `cacheprovider`, `doctest` and `legacypath`: collection runs ~14ms shorter,
  and the whole run is unchanged within noise.
- **A speed-oriented replacement for pytest** (surveyed 2026-11-03): none is a
  mature drop-in yet. The closest, pytest-rs, is measured in #pytest-rs; the
  others drop plugins, hooks or fixtures.

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

# Tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

This tracker covers the repo as a whole. Individual projects keep their own
trackers alongside their code, in subdirectories.

---

## Recurring maintenance

**Goal:** refresh what goes stale on its own, on a chosen cadence rather than by
surprise. Entries here never complete — a finished run leaves the task in place
for its next turn — so never prune them.

- [ ] **Refresh pinned dependencies** {#dependency-refresh} — about monthly, run
      `uv lock --upgrade && uv sync`, so everything this repo pins picks up
      improvements on a chosen schedule instead of drifting. `--dry-run`
      previews what would move, and the Stop checks report within one turn
      whether the new versions object to anything — read those before committing
      the lockfile.
  - Note: regenerate `convention_cards/requirements.txt` whenever a refresh
    moves one of that project's dependencies — Render deploys from that snapshot
    rather than from `uv.lock`, so the live webapp is otherwise left behind. The
    README's convention-card printing section carries the command.
  - Note: when a refresh moves `playwright`, run
    `.venv/bin/python -m playwright install chromium` to fetch the browser build
    the new version expects — each release is paired to one build. Run it once
    from every virtual environment that needs a browser, worktrees included:
    installing is also what registers that environment as a claimant, and
    Playwright deletes builds no registered environment claims. A registered
    environment's build is never taken, so the cleanup only reaps genuinely
    orphaned builds. And a duplicate install is a cheap cache hit.
  - Note: use `git log -1 --format=%as -- uv.lock` to determine when this last
    ran.

- [ ] **Review the `slow` annotations** {#slow-annotations} — about monthly,
      measure each test's latency against the budget described in
      `pyproject.toml`, and update the annotations to match.
  - Last run: 2026-10-21
  - Note: to measure, time several runs in the usual order and several in
    reverse, and start from the cheaper of each test's two medians, so that no
    test is charged in full for filling a shared cache first. Then amortize
    shared setup and cache costs across the tests that use them.
    - Tip: wrapping each `functools.cache` function in a pytest plugin shows
      what each cached result cost and which tests read it.
  - Rationale: a periodic review by hand is simpler, for now, than a
    `conftest.py` report or a check.

---

## Testing infrastructure

**Goal:** test code that touches the filesystem without cutting I/O seams into
production signatures for the tests' benefit.

- [ ] Adopt pyfakefs for the suites that read and write files, and retire the
      injected writers they were built around. {#fake-filesystem}
  - Rationale, measurements, the exclusion list, and the mechanics are in
    [faking-the-filesystem.md](faking-the-filesystem.md) — read it first; it was
    written from a live exploration and settles most of what this needs.
  - Note: mostly not a speed change. Writing real temporary directories costs
    about 11 ms across the whole suite, though pytest also deletes an earlier
    run's directories at the end of every run, which fewer files would shrink
    ([stop-hook-timing.md](stop-hook-timing.md#set-aside) #set-aside). The point
    is that `write` comes off three public signatures in `acbl_fetching` and
    `club_fetching`, and the real writer starts being exercised.
  - Note: three things are excluded and should stay on real paths — anything
    Pillow-based (a JPEG save silently writes zero bytes and sends the image to
    standard output), `private_paths` (shells out to git, which cannot run
    against a fake filesystem), and any test needing `tmp_path`.
  - Note: land the `conftest.py` guard that catches a test asking for both `fs`
    and `tmp_path`. Without it the pairing fails with a bare `/tmp` error naming
    neither fixture.
  - Note: `private_paths_test` moves too. Three of its tests build real
    directories through `tmp_path` so an existence check has something to find,
    and those directories are all a fake filesystem needs to hold. They have to
    drop `tmp_path` in the process, since it cannot be paired with `fs`.
  - Note: `traveller_store_test` is the biggest win of the three. Every test
    there writes a capture tree to disk, runs the store over it, and reads the
    records back — a full round trip through the filesystem per test, all of it
    small text files that a fake holds just as well. It drops `tmp_path` the
    same way the others do.
  - Note: leave `discover_private_tree`'s `find_checkout` seam alone. Git is the
    one dependency here that no filesystem fake replaces, so that parameter
    stays after the rest come off — see the document's section on choosing
    between the two.
- [ ] Once that lands, collapse `capture_urls`'s `sidecar_for` and
      `sidecar_contents` into a `write_sidecar` / `read_sidecar` pair that does
      its own I/O.
  - Rationale: the split exists only so a fetcher can hand a path and bytes to
    its injected writer. With the injection gone, the pair can read and write
    directly, which is the shape it wanted to begin with. Depends on
    #fake-filesystem.
  - Note: the module docstring argues for the current arrangement — that it
    hands out a path and some bytes rather than writing anything — so it needs
    rewriting in the same change, not left behind defending what was replaced.
  - Note: `read_url` already returns a `Read`, so `read_sidecar` inherits that
    and the empty-sidecar issue comes along unchanged.
- [ ] Amend `~/.claude/rules/testing.md`'s I/O-boundary rule in light of the
      same exploration.
  - Note: the rule says to restructure an entry point to accept a stream rather
    than mock a file, because hand-written mocks are brittle. A maintained
    filesystem fake is not brittle in that way, so the rule should keep the part
    that survives — take the decoded domain object rather than a handle to where
    it lives, as `transcribe_sheet` does — and send genuinely filesystem-shaped
    code to a fake instead of an invented injection seam.
  - Note: dotfiles changes need explicit permission for the specific edit, per
    CLAUDE.md, so this one is raised rather than done.

---

## Backlog

- [ ] **Consider contributing the pypdfium2 stubs to typeshed**
      {#typeshed-pypdfium2}: the acceptance criteria fit — pypdfium2 is on PyPI
      and ships no types of its own — and per
      [typeshed#15118](https://github.com/python/typeshed/issues/15118),
      pypdfium2's maintainers would rather the stubs live in typeshed than in
      the package. That issue's "not planned" closure is procedural, not a
      rejection: typeshed keeps no stub-request issues open, and its closing
      comment welcomes a contribution following `CONTRIBUTING.md`, with
      `create_baseline_stubs.py` to generate the starting point.
  - Note: a contribution means covering the public helpers API under typeshed's
    stubtest CI (the raw ctypes layer can stay a marked partial stub) and
    maintaining the stubs as pypdfium2 evolves. Either way `stubs/` stays until
    a published `types-pypdfium2` exists to swap in.

- [ ] Bring the older stub packages' header comments, and the `dev` group
      comments in `convention_cards/` and `system_notes/`, into line with the
      genanki stubs' wording: cite `stubs/README.md` by path rather than "two
      levels up", and say that uv installs the `dev` group by default.

- [ ] List the captured HTML fixtures in a `.prettierignore` at the repo root.
      {#prettier-ignores-fixtures}
  - Rationale: `session_analysis/testdata/travellers/` holds five files captured
    verbatim from live sites, and reformatting one silently changes what the
    parser tests are parsing. Prettier rewrote all five when it was pointed at
    `session_analysis/` during this session's wrap-up.
  - Note: the Stop hook does not reach them. `quiet-prettier.sh` with no
    arguments only offers `*.md`, `*.js` and `*.ts`, so the hazard appears only
    when someone passes a directory explicitly and prettier picks the HTML up on
    its own. An ignore file closes it at the source rather than relying on
    remembering.
  - Note: the repo has no `.prettierignore` and no project-level prettier
    config; `quiet-prettier.sh` falls back to `~/.prettierrc`. Adding an ignore
    file is a repo-local change and does not touch dotfiles.

- [ ] **[maybe] Freeze what collection loads, so garbage collection skips it**
      {#freeze-collected-objects} — a root `conftest.py` would pause garbage
      collection while pytest collects, then freeze everything collection
      loaded. Two variants, their measurements, and the tradeoffs they share are
      in [stop-hook-timing.md](stop-hook-timing.md#freeze-variants).
  - Note: Claude's lean is the variant that runs one full garbage collection
    before the freeze.

- [ ] **[maybe] Revisit pytest-rs once it matures** {#revisit-pytest-rs} — on
      the hook's tests it ran up to ~40% faster than pytest:
      [stop-hook-timing.md](stop-hook-timing.md#pytest-rs). The user is watching
      it passively, and wants it past alpha, with reasonable confidence in its
      quality, before it replaces pytest.
  - Note: the signs of maturity that would build confidence include: established
    projects outside its authors' own using it in their test runs, and a
    conda-forge or Linux distribution package of it. A prebuilt package for the
    repo's Python is a practical prerequisite.

- [ ] **Revisit prettier's experimental command line**
      {#prettier-experimental-cli} — under Bun it checks files in ~24ms, against
      ~62ms for prettier's usual command line, measured in
      [stop-hook-timing.md](stop-hook-timing.md#prettier-launches). Two gaps
      keep it out of `format.sh` for now: it exits 1 rather than 2 on a parse
      error or a missing file, which `format.sh` reads as a finding rather than
      breakage, and it has no `--find-config-path`.

- [~] **Salvage the paused dotfiles lane `stop-hook-timing`**
  {#salvage-timing-lane} — carry onto dotfiles `main` whatever of that lane's
  branch still applies, then remove its worktree and branch after a final pass,
  which the user wants before anything is removed.
  - Note: every piece carried over so far has landed, so the final pass is what
    remains.
  - Note: the review-pass tracker entry, in dotfiles worktree
    `review-pass-fold-task`, is deferred: the user expects its wording to take
    some iteration.
  - Note: the detached dotfiles worktree `stop-latency-check`, left from the
    dotfiles timing, can be removed along with the lane.
  - Note: Claude's assessment, not yet confirmed in the final pass: the rest is
    obsolete. That covers the Rust port of the chain and statusline,
    `gh-protect` in Rust, remembering which suites passed, and the lane's ANSI
    and `cargo test` tasks.

- [ ] **Keep the agent environment's `VIRTUAL_ENV` out of the Stop hook**
      {#session-virtual-env} — dotfiles' `zsh/.zshrc` activates
      `~/.venvs/default`, a Python 3.14 environment, in every interactive shell,
      so sessions and the Stop hook inherit `VIRTUAL_ENV` pointing at it while
      bridge runs on 3.15. Nothing reads the variable on purpose: `uv run`
      ignores it with a warning that opens mypy's halt output, and pytest-rs
      honors it, so 40 test files then fail to import.
  - Open question: the user prefers retiring the environment outright if nothing
    needs it, dotfiles `tasks.md` #retire-default-venv, and will come back to
    this after reviewing the pending branches. Narrower fixes, should retiring
    fall through: put the environment's `bin/` on PATH without activating it,
    which drops only the variable, or unset the variable in `stop_checks.sh`,
    which leaves mid-turn runs warning.
  - Note: what still used the environment on 2026-11-03, as seen from this
    account (the user's own was unreadable): crosswords' `clue-gen` command, and
    its `cluegen/scratch/finetune/*.sh`, which name the environment's Python and
    `optiq` by path; the synced pdf and skill-creator skills, whose scripts
    import pypdf, reportlab and yaml through a bare `python3`; bridge-private's
    font README, which names it for fontTools, now a bridge dependency; and
    throwaway scripts in sessions, using Pillow and pypdf, last on 2026-09-14.
  - Note: `uv run --no-active`, a flag uv accepts but leaves out of `--help`,
    silences the warning for one call; `-q` silences every warning.

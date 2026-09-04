# Tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

This tracker covers the repo as a whole. Individual projects keep their own
trackers alongside their code, in subdirectories.

---

## Recurring maintenance

**Goal:** keep what this repo depends on current, on a chosen cadence rather
than by surprise. Entries here never complete — a finished run leaves the task
in place for its next turn — so never prune them.

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

---

## Testing infrastructure

**Goal:** test code that touches the filesystem without cutting I/O seams into
production signatures for the tests' benefit.

- [ ] Adopt pyfakefs for the suites that read and write files, and retire the
      injected writers they were built around. {#fake-filesystem}
  - Rationale, measurements, the exclusion list, and the mechanics are in
    [faking-the-filesystem.md](faking-the-filesystem.md) — read it first; it was
    written from a live exploration and settles most of what this needs.
  - Note: not a speed change. Real temporary directories would cost about 11 ms
    across the whole suite. The point is that `write` comes off three public
    signatures in `acbl_fetching` and `club_fetching`, and the real writer
    starts being exercised.
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

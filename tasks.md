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
  - Note: use `git log -1 --format=%as -- uv.lock` to determine when this last
    ran.

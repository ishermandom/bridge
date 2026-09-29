# Bridge

## The private sibling repo {#bridge-private}

`bridge-private`, checked out beside this repo, holds what this public repo must
not: data that names club members (scoresheet scans, traveller captures, session
records and their transcripts), assets that are not freely redistributable, and
notes specific to the user's own bridge partnerships. The two repos are one
project, split only by what may be published. `bridge-private` mirrors this
repo's subproject directories by name, so `session_analysis/` keeps its private
data in `bridge-private/session_analysis/`. Each subproject locates that
directory through its own `private_paths.py`, whose docstring says what the
subproject keeps there.

- **Read anything in `bridge-private` whenever the work is in this repo**,
  without asking — the user has authorized it.
- **Before committing in `bridge-private` on its `main` branch**, ask the user,
  whatever the permission mode. Its work usually happens straight on `main`
  rather than in a worktree, so such a commit gets no review before it lands.
  The permission to commit freely in this repo does not carry over to
  `bridge-private`, even though the two are one project.
- **Before writing anything from `bridge-private` into a tracked file here** — a
  fixture, an example value, a cell quoted in a doc or comment — strip every
  club member's name and identifier, using placeholders such as `First Last`.
  This repo is public.
- **Before running a harness over real data**, point its output outside this
  checkout, so no member's data lands where a commit could sweep it up.

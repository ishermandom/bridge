# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Where this project's non-public data lives on disk.

Scoresheet scans, traveller captures, and every session reconciled from them
carry other club members' names and results, so none of it belongs in this
public repository. It lives in the `bridge-private` checkout beside this one
instead; travellers.md `#pii` says why, and spec.md settles the same question
from the sheet's side.

That repo names its subproject directories identically to this public repo, so
this project's data sits under `session_analysis`:

```text
bridge-private/session_analysis/
├── scoresheets/
│   ├── inbox/      scans waiting to be digitized
│   ├── archive/    scans already digitized
│   └── samples/    blank forms and stand-in photos, which nothing reads
├── travellers/
│   ├── raw/        captures, under a subdirectory per publishing site
│   └── parsed/     the travellers those captures parse into
└── sessions/       the reconciled records this pipeline exists to write
```

The trees divide by what they hold rather than by which stage touches them, so a
session's record sits apart from the scan it came from and outlives it.
"""

import dataclasses
import subprocess
from collections.abc import Callable
from pathlib import Path

# The capture root's subdirectories, one per publishing site. `traveller_store`
# picks a capture's parser from the directory it sits in, so a capture saved by
# hand belongs in the directory for the site it came from. The club's directory
# holds both formats that site publishes for a game — the PBN deal file and the
# HTML recap; their file extensions tell the two apart.
CLUB_CAPTURE_DIRECTORY = 'club'
ACBL_CLUB_CAPTURE_DIRECTORY = 'acbl_club'
ACBL_TOURNAMENT_CAPTURE_DIRECTORY = 'acbl_tournament'

_PRIVATE_CHECKOUT_NAME = 'bridge-private'
_PROJECT_DIRECTORY = 'session_analysis'


@dataclasses.dataclass(frozen=True)
class PrivateTree:
  """The layout of this project's private data.

  Holds nothing but the root, so every path below follows from it alone. Finding
  that root is `discover_private_tree`'s job, and the only part of this that
  depends on the machine it runs on.
  """

  # This project's directory inside the private checkout, not the checkout
  # itself — the checkout holds other projects' data alongside.
  root: Path

  @property
  def scan_inbox(self) -> Path:
    """Scans waiting to be digitized; a "process inbox" run reads these."""
    return self.root / 'scoresheets' / 'inbox'

  @property
  def scan_archive(self) -> Path:
    """Scans already digitized, kept so the pipeline can re-derive a record."""
    return self.root / 'scoresheets' / 'archive'

  @property
  def traveller_captures(self) -> Path:
    """Captures as fetched or hand-saved, under a subdirectory per site."""
    return self.root / 'travellers' / 'raw'

  @property
  def traveller_records(self) -> Path:
    """Parsed travellers, holding the durable game record as JSON."""
    return self.root / 'travellers' / 'parsed'

  @property
  def session_records(self) -> Path:
    """Reviewed sessions, as the `<session-key>.json` the analysis stage reads.

    These sit apart from the scans they were digitized from, because a record
    outlives the staging that produced it: a scan moves through `inbox` and into
    `archive`, while a record stays put.
    """
    return self.root / 'sessions'


def _this_checkout() -> Path:
  """The `bridge` checkout this file belongs to, according to git.

  A worktree under `.claude/worktrees/` has no `bridge-private` beside it, so
  the answer comes from the repository's common directory — shared by the main
  checkout and every worktree — rather than from this file's own path.
  """
  try:
    # `--path-format=absolute` so the answer does not depend on the cwd, and
    # `cwd` pinned to this file's directory so it does not depend on the
    # caller's either.
    completed = subprocess.run(
      ('git', 'rev-parse', '--path-format=absolute', '--git-common-dir'),
      cwd=Path(__file__).parent,
      capture_output=True,
      check=True,
      text=True,
    )
  except subprocess.CalledProcessError as error:
    raise RuntimeError(
      f'git could not name this checkout: {error.stderr.strip()}'
    ) from error
  except OSError as error:
    raise RuntimeError(
      f'could not run git to name this checkout: {error}'
    ) from error

  # The common directory is the checkout's `.git`, so its parent is the
  # checkout.
  return Path(completed.stdout.strip()).parent


def discover_private_tree(
  *, find_checkout: Callable[[], Path] = _this_checkout
) -> PrivateTree:
  """This project's private data tree, beside the checkout it accompanies.

  `bridge-private` sits next to the `bridge` checkout, and this project's data
  sits in a directory named for it inside that repo.

  Args:
    find_checkout: names the `bridge` checkout this file belongs to; injectable
      so a test needs no repository.

  Raises:
    RuntimeError: if git cannot name this checkout — it is missing, or this
      file no longer sits inside a repository.
    FileNotFoundError: if no `bridge-private` directory sits beside it.
  """
  checkout = find_checkout()
  private_checkout = checkout.parent / _PRIVATE_CHECKOUT_NAME
  if not private_checkout.is_dir():
    raise FileNotFoundError(
      f'no {_PRIVATE_CHECKOUT_NAME} directory at {private_checkout}; it is '
      f'expected beside the {checkout.name} checkout it accompanies'
    )
  return PrivateTree(private_checkout / _PROJECT_DIRECTORY)

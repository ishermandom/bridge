# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Where the assets kept in the private sibling repo live on disk.

The renderer's base artwork is ACBL's copyrighted card, and its fonts include
cuts that are not freely redistributable, so neither is committed to this public
repository. They live in the `bridge-private` checkout beside this one instead,
and the specimen scripts write their printed sheets back there, next to the
collections they compare.

One location covers all of it: the paths below are fixed subpaths of one
discovered checkout, so they cannot drift apart and there is a single thing to
repoint at a different checkout.
"""

import dataclasses
import subprocess
from pathlib import Path

_PRIVATE_CHECKOUT_NAME = 'bridge-private'


@dataclasses.dataclass(frozen=True)
class PrivateAssets:
  """The layout of the assets inside a `bridge-private` checkout.

  Carries no state beyond the root, so a test points one at a temporary
  directory rather than reaching for the real checkout.
  """

  root: Path

  @property
  def base_acbl_card_pdf(self) -> Path:
    """The official fillable ACBL card the renderer overlays entries onto."""
    return self.root / 'convention_cards' / 'acbl.pdf'

  @property
  def fonts_directory(self) -> Path:
    """The font collection: entry-face candidates and the HTML card's stack.

    `fonts/README.md` there records each file's provenance.
    """
    return self.root / 'convention_cards' / 'fonts'

  @property
  def palette_directory(self) -> Path:
    """Where the palette specimen writes its printed comparison sheet."""
    return self.root / 'convention_cards' / 'palette'


def discover_private_assets() -> PrivateAssets:
  """The private checkout beside this one, located through git.

  `bridge-private` sits next to the `bridge` checkout it accompanies. The
  `bridge` checkout is found through git's common directory rather than through
  this file's own path, because a worktree under `.claude/worktrees/` has no
  such sibling of its own — the common directory is shared by the main checkout
  and every worktree, so it names the same place from all of them.

  Raises:
    RuntimeError: if git cannot report the checkout.
    FileNotFoundError: if no `bridge-private` directory sits beside it.
  """
  try:
    # `cwd` pinned to this file's directory, so git reports on the repo this
    # module lives in no matter where the caller runs from. Without
    # `--path-format=absolute`, git does not promise an absolute answer;
    # absolute, the path stays valid anywhere.
    completed = subprocess.run(
      ('git', 'rev-parse', '--path-format=absolute', '--git-common-dir'),
      cwd=Path(__file__).parent,
      capture_output=True,
      check=True,
      text=True,
    )
  except (OSError, subprocess.CalledProcessError) as error:
    raise RuntimeError(
      f'could not locate the bridge checkout through git: {error}'
    ) from error

  # The common directory is the checkout's `.git`, so its parent is the checkout
  # and the sibling one level further up is what we are after.
  checkout = Path(completed.stdout.strip()).parent
  root = checkout.parent / _PRIVATE_CHECKOUT_NAME
  if not root.is_dir():
    raise FileNotFoundError(
      f'no {_PRIVATE_CHECKOUT_NAME} directory at {root}; it is expected '
      f'beside the {checkout.name} checkout it accompanies'
    )
  return PrivateAssets(root)

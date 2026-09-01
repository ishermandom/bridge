# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Fetch a date's travellers from the sites that publish them, and store them.

Capturing a session's official results takes two steps that already exist and
nothing drives from a command line: `club_fetching` and `acbl_fetching` download
what each site published for a date, and `traveller_store` parses the captures
on disk into the records the rest of the pipeline reads. This is the command
that runs both:

```shell
.venv/bin/python -m session_analysis.unreviewed.fetch_travellers 2026-06-29 \
    --player-number 2475316
```

A run fetches every source by default, since which of them published a given
session is not knowable before looking; `--source` narrows it. The sources are
independent: one that fails costs its own captures and nothing else, and the
store step still runs over whatever did land, so a Cloudflare timeout at ACBL
does not strand the club's files unparsed.

Storing is deliberately not limited to what this run fetched. `store_travellers`
walks the whole capture root and writes a record for every capture lacking a
current one, which is also what picks up a capture saved by hand — the
acquisition fallback for whatever a fetch cannot reach (travellers.md
`#acquisition`).
"""

import argparse
import datetime
import enum
import logging
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from playwright.sync_api import Error as PlaywrightError

from session_analysis import acbl_fetching, club_fetching, traveller_store
from session_analysis.models import Issue
from session_analysis.private_paths import (
  ACBL_CLUB_CAPTURE_DIRECTORY,
  ACBL_TOURNAMENT_CAPTURE_DIRECTORY,
  CLUB_CAPTURE_DIRECTORY,
  PrivateTree,
  discover_private_tree,
)

logger = logging.getLogger(__name__)


class Source(enum.StrEnum):
  """A site a run fetches a date's travellers from.

  Each member's value is the capture-root subdirectory that site's captures file
  under, which is what later picks the parser that reads them (travellers.md
  `#pii`).

  Coarser than `travellers.TravellerSource`, which additionally tells the club
  site's two published formats apart: one club fetch brings back both.
  """

  CLUB = CLUB_CAPTURE_DIRECTORY
  ACBL_CLUB = ACBL_CLUB_CAPTURE_DIRECTORY
  ACBL_TOURNAMENT = ACBL_TOURNAMENT_CAPTURE_DIRECTORY


# What a fetch fails with when a site, rather than this code, is what went
# wrong: the site or the network is unreachable (`OSError`, which covers
# `urllib`'s errors and a socket timeout), an index page is no longer the page
# it was taken for (`ValueError`), Cloudflare never clears (`RuntimeError`), or
# the browser itself will not start (`PlaywrightError`).
_FETCH_FAILURES = (OSError, ValueError, RuntimeError, PlaywrightError)


@dataclass(frozen=True)
class SourceOutcome:
  """What one source's fetch produced.

  `failure` holds what a fetch raised, and is None when the fetch ran to
  completion — including a completion with no captures at all, which is what a
  date that source published nothing for looks like.
  """

  source: Source
  captures: tuple[Path, ...] = ()
  failure: Exception | None = None


@dataclass(frozen=True)
class RunOutcome:
  """Everything one run did, for a caller to report and set an exit code from.

  `stored` and `issues` come from the single store pass a run ends with, so they
  cover every capture that needed parsing rather than only this run's fetches.
  """

  fetches: tuple[SourceOutcome, ...]
  stored: tuple[PurePosixPath, ...]
  issues: tuple[Issue, ...]

  @property
  def has_fetch_failures(self) -> bool:
    """Whether any source failed to fetch — a run's one failure condition.

    `issues` deliberately do not count. A capture that stores nothing reports
    itself again on every later run, since no record is ever written for it, so
    counting those would leave one gated ACBL game failing every run from then
    on.
    """
    return any(fetch.failure for fetch in self.fetches)


def _fetch_source(
  source: Source,
  player_number: str,
  date: datetime.date,
  destination: Path,
) -> Sequence[Path]:
  """Download one source's captures for `date` beneath `destination`.

  The club site publishes a date's games to everyone alike, so its fetch has no
  use for `player_number`; both ACBL surfaces index a player's results by it.
  """
  match source:
    case Source.CLUB:
      return club_fetching.fetch_travellers(date, destination)
    case Source.ACBL_CLUB:
      return acbl_fetching.fetch_club_travellers(
        player_number, date, destination
      )
    case Source.ACBL_TOURNAMENT:
      return acbl_fetching.fetch_tournament_travellers(
        player_number, date, destination
      )


class SourceFetch(Protocol):
  """Downloads one source's captures for a date, returning the paths written.

  The seam `fetch_and_store` reaches the network through: its default drives the
  real fetchers, and a test supplies its own so it needs neither the network nor
  a browser.
  """

  def __call__(
    self,
    source: Source,
    player_number: str,
    date: datetime.date,
    destination: Path,
  ) -> Sequence[Path]: ...


def fetch_and_store(
  *,
  sources: Iterable[Source],
  player_number: str,
  date: datetime.date,
  tree: PrivateTree,
  fetch_source: SourceFetch = _fetch_source,
) -> RunOutcome:
  """Fetch `date`'s captures from `sources`, then store the ones needing it.

  Args:
    sources: the sites to fetch, each saved beneath its own capture directory.
    player_number: the ACBL player number whose results to fetch.
    date: the date played.
    tree: the private tree the captures are saved into and the records written
      under.
    fetch_source: downloads one source's captures; injectable so a test needs
      neither the network nor a browser.

  Returns:
    What each source yielded, and what the store pass that follows wrote.
  """
  fetches = []
  for source in sources:
    try:
      captures = fetch_source(
        source,
        player_number,
        date,
        tree.traveller_captures / source.value,
      )
    except _FETCH_FAILURES as error:
      # One site being unreachable costs its own captures and nothing more: the
      # sources after it still run, and so does the store pass below.
      logger.error(f'fetching {source} failed: {error}')
      fetches.append(SourceOutcome(source, failure=error))
      continue
    fetches.append(SourceOutcome(source, tuple(captures)))

  stored: tuple[PurePosixPath, ...] = ()
  issues: tuple[Issue, ...] = ()
  try:
    parsed = traveller_store.store_travellers(tree)
  except FileNotFoundError as error:
    # No capture root to walk: nothing has ever been fetched on this machine,
    # and this run brought nothing back either.
    logger.warning(f'nothing to parse: {error}')
  else:
    stored = tuple(parsed.value)
    issues = parsed.issues

  return RunOutcome(tuple(fetches), stored, issues)


def summarize(outcome: RunOutcome) -> str:
  """A run's result as the lines a person reads at the end of it.

  Every source gets a line, whether or not it brought anything back: a date a
  site published nothing for is worth saying as plainly as one that landed
  files.
  """
  label_width = max((len(fetch.source) for fetch in outcome.fetches), default=0)
  lines = []
  for fetch in outcome.fetches:
    label = fetch.source.ljust(label_width)
    if fetch.failure:
      lines.append(
        f'{label}  fetch failed — '
        f'{type(fetch.failure).__name__}: {fetch.failure}'
      )
    else:
      lines.append(f'{label}  captures: {len(fetch.captures)}')

  lines.append('')
  lines.append(f'records stored: {len(outcome.stored)}')
  lines.extend(f'  {record}' for record in outcome.stored)

  lines.append('')
  lines.append(f'issues: {len(outcome.issues)}')
  lines.extend(
    f'  {issue.severity} {issue.code}: {issue.message}'
    for issue in outcome.issues
  )
  return '\n'.join(lines)


def _iso_date(value: str) -> datetime.date:
  """Read a `YYYY-MM-DD` command-line argument as the date it names."""
  try:
    return datetime.date.fromisoformat(value)
  except ValueError as error:
    raise argparse.ArgumentTypeError(
      f'not a YYYY-MM-DD date: {value!r}'
    ) from error


def main(argv: Sequence[str] | None = None) -> int:
  """Parse arguments, fetch and store the date's travellers, and report.

  Takes `argv` and returns an exit code, following
  `club_sites/palo_alto/verify_live.py` rather than the plainer
  `convention_cards/make_card.py`: a run can partly fail, which needs both an
  exit code to carry that and an entry point a test can call.
  """
  parser = argparse.ArgumentParser(
    description="Fetch a date's travellers from the sites that publish them, "
    'and store the records they parse into.'
  )
  parser.add_argument(
    'date', type=_iso_date, help='the date played, as YYYY-MM-DD'
  )
  parser.add_argument(
    '--player-number',
    required=True,
    help='the ACBL player number whose results to fetch; the club site '
    'publishes to everyone alike and ignores it',
  )
  parser.add_argument(
    '--source',
    dest='sources',
    type=Source,
    choices=tuple(Source),
    action='append',
    help='fetch only this source; repeatable. Defaults to every source, '
    'since which of them published a session is not knowable before looking',
  )
  args = parser.parse_args(argv)

  # The command is the application, so it is where the fetchers' progress
  # logging gets somewhere to go.
  logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

  outcome = fetch_and_store(
    sources=args.sources or tuple(Source),
    player_number=args.player_number,
    date=args.date,
    tree=discover_private_tree(),
  )
  print(summarize(outcome))
  return 1 if outcome.has_fetch_failures else 0


if __name__ == '__main__':
  sys.exit(main())

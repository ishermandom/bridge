# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the command that fetches a date's travellers and stores them.

What is under test is what the command itself decides: which capture directory
each source files under, what one source's failure costs the others, and what
the closing summary says. The fetching and the parsing behind it have their own
tests, so `_Sites` stands in for the real sites — writing scripted captures
where a real fetch would have written them, so the store step that follows runs
for real against the committed fixtures.

`main` is left out: it is argparse plus glue over the two functions below, and
running it would reach for the real private tree beside this checkout.
"""

import datetime
import logging
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

import pytest

from session_analysis.enums import IssueSeverity
from session_analysis.models import Issue
from session_analysis.private_paths import PrivateTree
from session_analysis.unreviewed.fetch_travellers import (
  RunOutcome,
  Source,
  SourceOutcome,
  fetch_and_store,
  summarize,
)

# The capture fixtures sit beside the parsers that read them, in the package
# root rather than in this directory.
TESTDATA = Path(__file__).parent.parent / 'testdata/travellers'


def _fixture(name: str) -> str:
  """One committed capture fixture's whole text."""
  return (TESTDATA / name).read_text()


class _Sites:
  """A stand-in for the publishing sites, in place of the real fetch.

  Writes each source's scripted captures into the destination it is handed,
  where a real fetch would have written them, and raises for a source scripted
  to fail. Records which sources it was asked for, in order, so a test can see
  that a failure cost only its own source.
  """

  def __init__(
    self,
    captures: Mapping[Source, Mapping[str, str]] | None = None,
    failures: Mapping[Source, Exception] | None = None,
  ) -> None:
    self._captures = captures or {}
    self._failures = failures or {}
    self.fetched: list[Source] = []

  def fetch(
    self,
    source: Source,
    player_number: str,
    date: datetime.date,
    destination: Path,
  ) -> Sequence[Path]:
    """Write `source`'s scripted captures beneath `destination`."""
    self.fetched.append(source)
    if source in self._failures:
      raise self._failures[source]

    written = []
    for relative_path, contents in self._captures.get(source, {}).items():
      capture = destination / relative_path
      capture.parent.mkdir(parents=True, exist_ok=True)
      capture.write_text(contents)
      written.append(capture)
    return tuple(written)


def _run(
  tree: PrivateTree,
  sites: _Sites,
  *,
  sources: Iterable[Source] = tuple(Source),
) -> RunOutcome:
  """A run against `sites`, with the arguments no test turns on filled in."""
  return fetch_and_store(
    sources=sources,
    player_number='1234567',
    date=datetime.date(2026, 6, 29),
    tree=tree,
    fetch_source=sites.fetch,
  )


# --- fetching ---


def test_each_source_saves_beneath_its_own_capture_directory(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  sites = _Sites(
    {
      Source.CLUB: {'gameresults2/vi/D260629M.pbn': '[Event "Monday"]\n'},
      Source.ACBL_CLUB: {'my.acbl.org/details/1441256.html': '<html></html>'},
      Source.ACBL_TOURNAMENT: {'live.acbl.org/1/summary.html': '<html></html>'},
    }
  )

  _run(tree, sites)

  captures = tree.traveller_captures
  assert (captures / 'club/gameresults2/vi/D260629M.pbn').is_file()
  assert (captures / 'acbl_club/my.acbl.org/details/1441256.html').is_file()
  assert (captures / 'acbl_tournament/live.acbl.org/1/summary.html').is_file()


def test_only_the_named_sources_are_fetched(tmp_path: Path) -> None:
  sites = _Sites()

  _run(PrivateTree(tmp_path), sites, sources=[Source.CLUB])

  assert sites.fetched == [Source.CLUB]


def test_an_unnarrowed_run_fetches_every_source(tmp_path: Path) -> None:
  sites = _Sites()

  _run(PrivateTree(tmp_path), sites)

  assert sites.fetched == [
    Source.CLUB,
    Source.ACBL_CLUB,
    Source.ACBL_TOURNAMENT,
  ]


# --- one source failing ---


def test_a_failed_source_does_not_stop_the_ones_after_it(
  tmp_path: Path,
) -> None:
  sites = _Sites(failures={Source.CLUB: OSError('club site unreachable')})

  _run(PrivateTree(tmp_path), sites)

  assert sites.fetched == [
    Source.CLUB,
    Source.ACBL_CLUB,
    Source.ACBL_TOURNAMENT,
  ]


def test_a_failed_source_carries_what_it_raised(tmp_path: Path) -> None:
  sites = _Sites(
    failures={Source.ACBL_CLUB: RuntimeError('Cloudflare never cleared')}
  )

  outcome = _run(PrivateTree(tmp_path), sites, sources=[Source.ACBL_CLUB])

  assert outcome.has_fetch_failures
  assert str(outcome.fetches[0].failure) == 'Cloudflare never cleared'


def test_a_source_that_published_nothing_is_not_a_failure(
  tmp_path: Path,
) -> None:
  sites = _Sites()

  outcome = _run(PrivateTree(tmp_path), sites, sources=[Source.CLUB])

  assert not outcome.has_fetch_failures
  assert outcome.fetches[0].captures == ()


def test_captures_are_stored_even_when_another_source_failed(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  sites = _Sites(
    captures={
      Source.CLUB: {'gameresults2/vi/D260629M.pbn': _fixture('club_game.pbn')}
    },
    failures={Source.ACBL_CLUB: RuntimeError('Cloudflare never cleared')},
  )

  outcome = _run(tree, sites, sources=[Source.CLUB, Source.ACBL_CLUB])

  assert outcome.stored == (PurePosixPath('club/gameresults2/vi/D260629M.pbn'),)


# --- storing ---


def test_a_fetched_capture_is_stored_as_a_record(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  sites = _Sites(
    {
      Source.ACBL_TOURNAMENT: {
        'live.acbl.org/1/summary.html': _fixture('acbl_tournament_session.html')
      }
    }
  )

  outcome = _run(tree, sites, sources=[Source.ACBL_TOURNAMENT])

  assert outcome.stored == (
    PurePosixPath('acbl_tournament/live.acbl.org/1/summary.html'),
  )
  record = 'acbl_tournament/live.acbl.org/1/summary.html.json'
  assert (tree.traveller_records / record).is_file()


def test_a_capture_saved_by_hand_is_stored_though_no_source_fetched_it(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  # The acquisition fallback: a capture dropped into a site's directory by hand,
  # which nothing this run fetched knows anything about.
  hand_saved = tree.traveller_captures / 'club/gameresults2/vi/D260629M.pbn'
  hand_saved.parent.mkdir(parents=True)
  hand_saved.write_text(_fixture('club_game.pbn'))

  outcome = _run(tree, _Sites(), sources=[Source.ACBL_TOURNAMENT])

  assert outcome.stored == (PurePosixPath('club/gameresults2/vi/D260629M.pbn'),)


def test_a_capture_root_that_does_not_exist_yet_stores_nothing(
  tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
  with caplog.at_level(logging.WARNING):
    outcome = _run(PrivateTree(tmp_path), _Sites(), sources=[Source.CLUB])

  assert outcome.stored == ()
  assert 'nothing to parse' in caplog.text


# --- the summary ---


def test_summary_counts_a_source_that_published_nothing() -> None:
  outcome = RunOutcome((SourceOutcome(Source.CLUB),), (), ())

  assert 'club  captures: 0' in summarize(outcome)


def test_summary_names_a_source_that_failed() -> None:
  outcome = RunOutcome(
    (
      SourceOutcome(
        Source.ACBL_CLUB, failure=RuntimeError('Cloudflare never cleared')
      ),
    ),
    (),
    (),
  )

  summary = summarize(outcome)

  assert 'acbl_club' in summary
  assert 'RuntimeError: Cloudflare never cleared' in summary


def test_summary_lists_the_records_stored() -> None:
  outcome = RunOutcome(
    (SourceOutcome(Source.CLUB),),
    (PurePosixPath('club/gameresults2/vi/D260629M.pbn'),),
    (),
  )

  summary = summarize(outcome)

  assert 'records stored: 1' in summary
  assert '  club/gameresults2/vi/D260629M.pbn' in summary


def test_summary_reports_what_the_store_could_not_read() -> None:
  outcome = RunOutcome(
    (SourceOutcome(Source.ACBL_CLUB),),
    (),
    (
      Issue(
        code='capture_held_no_boards',
        severity=IssueSeverity.MEDIUM,
        message='acbl_club/1430431.html holds no boards',
        location='capture',
      ),
    ),
  )

  summary = summarize(outcome)

  assert 'issues: 1' in summary
  assert 'capture_held_no_boards' in summary

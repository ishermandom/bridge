# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for fetching a player's travellers from ACBL Live.

The index markup here reproduces the real pages' shape — a DataTables table
whose first cell is the date and whose "Links" cell links to each session's
traveller among its other views — because that shape is what the parsing has to
survive, including the tournament summary anchor's two `class` attributes.

`fetch_tournament_travellers` and `fetch_club_travellers` are exercised through
`_Recorder`, which serves the pages a fetch would return and records what a
write would save — so tests touch neither a browser, the network, nor the disk.
Player number, ids, and names are placeholders; on the real site they are a
member's own number and their games.
"""

import datetime
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from session_analysis.acbl_fetching import (
  fetch_club_travellers,
  fetch_tournament_travellers,
)

_JUNE_27 = datetime.date(2026, 6, 27)
_JULY_20 = datetime.date(2026, 7, 20)
_PLAYER_NUMBER = '1234567'


def _make_index(
  table_id: str, headers: Sequence[str], rows: Sequence[str]
) -> str:
  """A results page whose `table_id` DataTables table holds `rows`."""
  head = ''.join(f'<th>{name}</th>' for name in headers)
  return (
    '<html><head><meta charset="utf-8"></head><body>'
    f'<table id="{table_id}" class="table table-striped dataTable">'
    f'<thead><tr>{head}</tr></thead>'
    f'<tbody>{"".join(rows)}</tbody>'
    '</table></body></html>'
  )


def _tournament_row(
  date: str,
  summary_href: str,
  *,
  tournament: str = 'Placeholder Open Sectional',
  event: str = 'Open Pairs',
  session: str = '10:00 am',
) -> str:
  """A tournament index row, faithful to the real markup: single-quoted
  attributes and the summary anchor's two `class` attributes (which HTML parsers
  collapse, so the summary is found by its href), among the session's other view
  links.

  Only the first (date) cell and the links cell are read. The rest reproduce the
  real column layout as filler — a deliberately far-off "Last Updated" date (so
  it is never mistaken for a test date), and the `%`/`mps`/`color` cells left
  blank as the real rows leave them depending on session type.
  """
  results_href = summary_href.replace('/summary', '/results')
  recap_href = summary_href.replace('/summary', '/recap')
  return (
    '<tr>'
    f'<td>{date}</td><td>{tournament}</td><td>{event}</td><td>{session}</td>'
    "<td data-timestamp='946684800'>01/01/2000 12:00 AM</td>"
    '<td>50.00</td><td></td><td></td>'
    "<td class='links'>"
    f"<a class='summary' href='{summary_href}' class=''>Summary</a>"
    f"|<a class='overalls' href='{results_href}'>Overalls</a>"
    f"|<a class='recaps' href='{recap_href}'>Recaps</a>"
    '</td></tr>'
  )


def _make_tournament_index(*rows: str) -> str:
  """A `live.acbl.org/player-results` page with `rows` in its events table."""
  return _make_index(
    'events',
    (
      'Date',
      'Tournament',
      'Event',
      'Session',
      'Last Updated',
      '%',
      'mps',
      'Color',
      'Links',
    ),
    rows,
  )


def _club_row(
  date: str,
  detail_href: str,
  *,
  club: str = 'Placeholder Bridge Club',
  event: str = 'Open Pairs',
  session: str = 'Morning',
) -> str:
  """A club index row: a `YYYY-MM-DD` date and a `club-results/details/<id>`
  link.

  As with `_tournament_row`, only the date and the link are read; the other
  cells (a far-off "Last Updated" date, score, mps, color) are filler in the
  real column layout, some blank as the real rows leave them.
  """
  return (
    '<tr>'
    f'<td>{date}</td><td>{club}</td><td>{event}</td><td>{session}</td>'
    "<td data-timestamp='946684800'>2000-01-01 12:00 AM</td>"
    '<td>55.00</td><td></td><td></td>'
    f"<td class='links'><a href='{detail_href}'>Results</a></td>"
    '<td></td></tr>'
  )


def _make_club_index(*rows: str) -> str:
  """A `my.acbl.org/club-results/my-results` page holding `rows`."""
  return _make_index(
    'results-table',
    (
      'Date',
      'Club Name',
      'Event',
      'Session',
      'Last Updated',
      'Score',
      'mps',
      'Color',
      'Links',
      'Personal Scores',
    ),
    rows,
  )


class _Recorder:
  """An in-memory stand-in for the fetcher's two seams — it serves the pages a
  fetch would return and records what a write would save — so tests touch
  neither a browser, the network, nor the disk.

  `fetch` returns the index for any non-traveller URL, and for a traveller URL
  (a `.../summary` or `.../details/<id>` path) the scripted body `bodies`
  supplies (keyed by host and path) or a stand-in. `write` records the saved
  path and bytes.
  """

  def __init__(
    self,
    index: str | bytes,
    *,
    bodies: Mapping[str, bytes] | None = None,
    destination: Path = Path('root'),
  ) -> None:
    self._index = index.encode() if isinstance(index, str) else index
    self._bodies = dict(bodies or {})
    self.destination = destination
    self.fetched: list[str] = []
    self.written: dict[str, bytes] = {}
    self.returned: Sequence[Path] = ()

  def fetch(self, url: str) -> bytes:
    self.fetched.append(url)
    parts = urllib.parse.urlsplit(url)
    is_traveller = parts.path.endswith('/summary') or '/details/' in parts.path
    if not is_traveller:
      return self._index
    return self._bodies.get(
      parts.netloc + parts.path, b'stand-in for ' + url.encode()
    )

  def write(self, path: Path, data: bytes) -> None:
    self.written[path.relative_to(self.destination).as_posix()] = data


def _run(
  fetch_func: Callable[..., Sequence[Path]],
  index: str | bytes,
  *,
  date: datetime.date,
  player_number: str = _PLAYER_NUMBER,
  bodies: Mapping[str, bytes] | None = None,
) -> _Recorder:
  """Fetch a player's travellers in memory; the recorder captures what happened.

  `recorder.written` maps each saved path (relative to the destination) to its
  bytes, in fetch order; `recorder.fetched` is every URL requested;
  `recorder.returned` is the paths the fetch returned.
  """
  recorder = _Recorder(index, bodies=bodies)
  recorder.returned = fetch_func(
    player_number,
    date,
    recorder.destination,
    fetch=recorder.fetch,
    write=recorder.write,
  )
  return recorder


# --- tournaments: selecting a date's sessions ---


def test_only_the_requested_tournament_sessions_are_fetched() -> None:
  index = _make_tournament_index(
    _tournament_row('06/28/2026', '/event/1000001/281D/2/summary'),
    _tournament_row('06/27/2026', '/event/1000001/27OP/2/summary'),
    _tournament_row('06/27/2026', '/event/1000001/27OP/1/summary'),
  )

  recorder = _run(fetch_tournament_travellers, index, date=_JUNE_27)

  # The 06/28 session is left untouched; only the two 06/27 sessions are saved.
  assert list(recorder.written) == [
    'live.acbl.org/event/1000001/27OP/2/summary.html',
    'live.acbl.org/event/1000001/27OP/1/summary.html',
  ]


def test_a_day_the_player_did_not_play_writes_nothing() -> None:
  index = _make_tournament_index(
    _tournament_row('06/28/2026', '/event/1000001/281D/2/summary'),
  )

  recorder = _run(
    fetch_tournament_travellers, index, date=_JUNE_27, player_number='7654321'
  )

  assert recorder.written == {}
  # Only the index is fetched — no traveller request is made.
  assert recorder.fetched == ['https://live.acbl.org/player-results/7654321']


def test_the_saved_paths_are_returned() -> None:
  # The public return value is the paths the fetch saved, so a caller can act on
  # what it just fetched; here two sessions on the requested date.
  index = _make_tournament_index(
    _tournament_row('06/27/2026', '/event/1000001/27OP/2/summary'),
    _tournament_row('06/27/2026', '/event/1000001/27OP/1/summary'),
  )

  recorder = _run(fetch_tournament_travellers, index, date=_JUNE_27)

  assert [path.as_posix() for path in recorder.returned] == [
    'root/live.acbl.org/event/1000001/27OP/2/summary.html',
    'root/live.acbl.org/event/1000001/27OP/1/summary.html',
  ]


# --- tournaments: saving the capture ---


def test_summary_html_is_saved_at_its_host_qualified_path() -> None:
  index = _make_tournament_index(
    _tournament_row('06/27/2026', '/event/1000001/27OP/2/summary'),
  )

  recorder = _run(
    fetch_tournament_travellers,
    index,
    date=_JUNE_27,
    bodies={'live.acbl.org/event/1000001/27OP/2/summary': b'<html>t</html>'},
  )

  # The traveller's own HTML is saved, and nothing else beside it.
  assert recorder.written == {
    'live.acbl.org/event/1000001/27OP/2/summary.html': b'<html>t</html>'
  }


def test_the_tournament_index_uses_the_player_results_path() -> None:
  recorder = _run(
    fetch_tournament_travellers,
    _make_tournament_index(),
    date=_JUNE_27,
    player_number='7654321',
  )

  assert recorder.fetched[0] == 'https://live.acbl.org/player-results/7654321'


# --- club games ---


def test_only_the_requested_days_club_games_are_fetched() -> None:
  index = _make_club_index(
    _club_row('2026-07-20', '/club-results/details/1484015'),
    _club_row('2026-07-14', '/club-results/details/1480637'),
  )

  recorder = _run(fetch_club_travellers, index, date=_JULY_20)

  # The 07/14 game is left untouched; the 07/20 detail page is saved under the
  # my.acbl.org host, its `YYYY-MM-DD` date parsed and its detail link followed.
  assert list(recorder.written) == [
    'my.acbl.org/club-results/details/1484015.html'
  ]


def test_the_club_index_uses_the_my_results_path() -> None:
  recorder = _run(
    fetch_club_travellers,
    _make_club_index(),
    date=_JULY_20,
    player_number='7654321',
  )

  assert recorder.fetched[0] == (
    'https://my.acbl.org/club-results/my-results/7654321'
  )


# --- rejecting a page that is not the index ---


def test_a_page_without_the_index_table_is_rejected() -> None:
  with pytest.raises(ValueError, match='results-table'):
    _run(
      fetch_club_travellers,
      '<html><body><p>nope</p></body></html>',
      date=_JULY_20,
    )


# --- a changed layout ---


def test_rows_without_a_traveller_link_warn_of_a_layout_change(
  caplog: pytest.LogCaptureFixture,
) -> None:
  # A row whose only links are an off-site summary and an on-site non-summary
  # view: neither is an on-site traveller, so no session is read. A table of
  # only such rows means the layout the parser keys on has changed.
  row = (
    '<tr><td>06/27/2026</td>'
    "<td class='links'>"
    "<a class='summary' href='https://example.com/event/1/OP/2/summary'>x</a>"
    "<a class='overalls' href='/event/1000001/27OP/2/results'>Overalls</a>"
    '</td></tr>'
  )

  with caplog.at_level('WARNING'):
    recorder = _run(
      fetch_tournament_travellers, _make_tournament_index(row), date=_JUNE_27
    )

  assert recorder.written == {}
  assert 'layout' in caplog.text


def test_an_unreadable_date_row_is_skipped_and_the_rest_kept(
  caplog: pytest.LogCaptureFixture,
) -> None:
  index = _make_tournament_index(
    _tournament_row('06/27/2026', '/event/1000001/27OP/2/summary'),
    _tournament_row('not-a-date', '/event/1000001/27OP/1/summary'),
    _tournament_row('06/27/2026', '/event/1000001/26OP/2/summary'),
  )

  with caplog.at_level('WARNING'):
    recorder = _run(fetch_tournament_travellers, index, date=_JUNE_27)

  # The middle row's date won't parse, so it is skipped and logged; the good
  # rows on either side are still fetched.
  assert list(recorder.written) == [
    'live.acbl.org/event/1000001/27OP/2/summary.html',
    'live.acbl.org/event/1000001/26OP/2/summary.html',
  ]
  assert 'date' in caplog.text

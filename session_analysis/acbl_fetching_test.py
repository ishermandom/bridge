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
from playwright.sync_api import Error as PlaywrightError

from session_analysis import capture_urls
from session_analysis.acbl_fetching import (
  _BrowserFetcher,
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
    self.urls: dict[str, str] = {}
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
    # The fetchers write a capture and its URL sidecar through this one writer,
    # as they would to a real directory; sorting the two apart here allows tests
    # to assert on either without filtering.
    relative = path.relative_to(self.destination).as_posix()
    if path.suffix == capture_urls.URL_SUFFIX:
      capture = relative.removesuffix(capture_urls.URL_SUFFIX)
      self.urls[capture] = data.decode().strip()
    else:
      self.written[relative] = data


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
  `recorder.urls` maps each saved path to the URL recorded beside it;
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


# --- recording where a capture came from ---


def test_each_saved_traveller_records_the_url_it_came_from() -> None:
  index = _make_tournament_index(
    _tournament_row('06/27/2026', '/event/1000001/27OP/1/summary'),
  )

  recorder = _run(fetch_tournament_travellers, index, date=_JUNE_27)

  # The saved path gains a `.html` the URL does not carry, so the sidecar is the
  # only place the fetched URL survives.
  assert recorder.urls == {
    'live.acbl.org/event/1000001/27OP/1/summary.html': (
      'https://live.acbl.org/event/1000001/27OP/1/summary'
    )
  }


def test_a_club_game_records_its_detail_page_url() -> None:
  index = _make_club_index(_club_row('2026-07-20', '/club-results/details/42'))

  recorder = _run(fetch_club_travellers, index, date=_JULY_20)

  assert recorder.urls == {
    'my.acbl.org/club-results/details/42.html': (
      'https://my.acbl.org/club-results/details/42'
    )
  }


# --- waiting out the challenge ---


class _FakeBrowser:
  """A `_Browser` serving scripted tab titles and page reads.

  Stands in for a real browser so the sequence a fetch follows — waiting out the
  challenge, reading, retrying — can be exercised without one. Titles are
  consumed one per poll, so a script reads as the tab's own history: what the
  page was called first, and what it became. The last entry of either script
  repeats, the way a settled page keeps its title.
  """

  def __init__(
    self,
    titles: Sequence[str] = ('A page',),
    reads: Sequence[bytes | Exception] = (b'<html>the page</html>',),
  ) -> None:
    self._titles = list(titles)
    self._reads = list(reads)
    self.started = False
    self.opened: list[str] = []
    self.closed_tabs: list[str] = []
    self.quit_called = False

  def start(self) -> None:
    self.started = True

  def request(self, path: str, *, decode: bool = True) -> object:
    if path.startswith('/json/close/'):
      self.closed_tabs.append(path.rsplit('/', 1)[1])
      return None
    title = self._titles.pop(0) if len(self._titles) > 1 else self._titles[0]
    return [{'id': self.opened[-1], 'title': title}]

  def open_tab(self, url: str) -> str:
    self.opened.append(f'tab-{len(self.opened)}')
    return self.opened[-1]

  def read_page(self, url: str) -> bytes:
    read = self._reads.pop(0) if len(self._reads) > 1 else self._reads[0]
    if isinstance(read, Exception):
      raise read
    return read

  def quit(self) -> None:
    self.quit_called = True


def _fetch(
  browser: _FakeBrowser, url: str = 'https://live.acbl.org/x'
) -> bytes:
  """Fetch through `browser`, with no real waiting between polls."""
  return _BrowserFetcher(browser, sleep=lambda _: None).fetch(url)


def test_a_page_that_clears_the_challenge_is_read() -> None:
  browser = _FakeBrowser(
    titles=['', 'Just a moment...', 'ACBL Live'],
    reads=[b'<html>the real page</html>'],
  )

  assert _fetch(browser) == b'<html>the real page</html>'


def test_an_unpainted_tab_is_not_mistaken_for_a_cleared_one() -> None:
  # An empty title is a tab that has not painted, and reading then would capture
  # nothing, so the wait has to outlast it.
  browser = _FakeBrowser(
    titles=['', '', 'ACBL Live'], reads=[b'<html>ok</html>']
  )

  assert _fetch(browser) == b'<html>ok</html>'


def test_a_challenge_that_never_clears_reports_the_titles_it_saw() -> None:
  browser = _FakeBrowser(titles=['Just a moment...'])

  with pytest.raises(RuntimeError, match='titles seen'):
    _fetch(browser)

  # One tab per attempt, each closed rather than left to accumulate.
  assert len(browser.opened) == 3
  assert browser.closed_tabs == browser.opened


# --- what a retry is for ---


def test_a_read_that_comes_back_as_a_challenge_is_retried() -> None:
  # The read is its own request, so it can draw a challenge of its own even
  # after the tab in front of it cleared one. Retrying keeps that interstitial
  # out of the capture.
  browser = _FakeBrowser(
    reads=[b'<html><title>Just a moment...</title></html>', b'<html>ok</html>']
  )

  assert _fetch(browser) == b'<html>ok</html>'


def test_a_page_giving_way_under_the_read_is_retried() -> None:
  # Cloudflare re-navigating the tab mid-read surfaces as a Playwright error,
  # which should cost one attempt rather than the whole source.
  browser = _FakeBrowser(
    reads=[
      PlaywrightError('Execution context was destroyed'),
      b'<html>ok</html>',
    ]
  )

  assert _fetch(browser) == b'<html>ok</html>'


def test_reads_that_never_succeed_fail_with_the_last_error_as_the_cause() -> (
  None
):
  browser = _FakeBrowser(reads=[PlaywrightError('page gone')])

  with pytest.raises(RuntimeError, match='3 attempts') as raised:
    _fetch(browser)

  assert isinstance(raised.value.__cause__, PlaywrightError)


def test_a_tab_that_will_not_close_does_not_replace_the_real_failure() -> None:
  class _UnclosableBrowser(_FakeBrowser):
    """Refuses to close tabs, as a browser that has died would."""

    def request(self, path: str, *, decode: bool = True) -> object:
      if path.startswith('/json/close/'):
        raise OSError('browser is gone')
      return super().request(path, decode=decode)

  browser = _UnclosableBrowser(titles=['Just a moment...'])

  # The challenge failure survives; the closing error does not displace it.
  with pytest.raises(RuntimeError, match='titles seen'):
    _fetch(browser)


# --- the browser's lifecycle ---


def test_the_browser_starts_once_across_several_fetches() -> None:
  browser = _FakeBrowser()
  fetcher = _BrowserFetcher(browser, sleep=lambda _: None)

  fetcher.fetch('https://live.acbl.org/one')
  fetcher.fetch('https://live.acbl.org/two')

  # Two tabs, one browser: the second fetch reuses whatever clearance the first
  # earned.
  assert len(browser.opened) == 2
  assert browser.started


def test_leaving_the_context_quits_the_browser() -> None:
  browser = _FakeBrowser()

  with _BrowserFetcher(browser, sleep=lambda _: None) as fetcher:
    fetcher.fetch('https://live.acbl.org/x')

  assert browser.quit_called

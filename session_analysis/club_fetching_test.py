# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for fetching published game-result files from the club site.

The calendar markup here reproduces the shapes the real page uses —
single-quoted attributes, the server's own file-existence probes left behind as
comments, games separated only by a line break, and file links written both
directly and through the download wrapper — because those shapes are exactly
what the parsing has to survive.

`fetch_travellers` is exercised through `_Recorder`, which serves one calendar
page and a stand-in body for each file fetched and records what would be written
— so tests touch neither the network nor the disk. Director directories are
placeholders (`alpha`, `beta`); on the real site they are the directors' own
names.
"""

import datetime
import logging
import urllib.parse
from collections.abc import Mapping
from pathlib import Path

import pytest

from session_analysis.club_fetching import fetch_travellers

_JUNE_29 = datetime.date(2026, 6, 29)
_CLUB_BASE_URL = 'https://paloaltobridge.org/'

# The calendar lives under this path; every other URL the fetcher requests is a
# file, which lets `_Recorder` tell the two apart without counting fetches.
_CALENDAR_URL_PREFIX = _CLUB_BASE_URL + 'game-results/'


def _make_calendar_page(
  entries: str,
  *,
  day: str = '29',
  month_heading: str = 'June 2026',
  charset: str = 'utf-8',
) -> str:
  """A calendar page carrying `entries` in one day's cell.

  `day` is the day number as the page prints it, so a test can write the
  spellings the real calendar might use rather than only a bare integer.
  """
  return (
    '<html>\n'
    f'<head><meta charset="{charset}"></head>\n'
    '<body>\n'
    f'<h2 style="text-align: center;"> Game Results for {month_heading} </h2>\n'
    "<table><tr class='calendar'>\n"
    "<td class='day'>\n"
    f"  <div class='cdate'> {day} </div>\n"
    # The server leaves its per-file existence probes in the cell as comments.
    f"  <div class='cinfo'><!--260629M.TXT does exist!-->{entries}</div>\n"
    '</td>\n'
    '</tr></table>\n'
    '</body></html>\n'
  )


class _Recorder:
  """An in-memory stand-in for the club site: serves one calendar page and a
  body per file fetched, and records what would be written to disk.

  A request under the `game-results/` path returns the calendar; any other URL
  is a file fetch, returning the test's scripted body when `bodies` supplies one
  (keyed by site-relative path), else a stand-in.
  """

  def __init__(
    self,
    calendar: str | bytes,
    *,
    bodies: Mapping[str, bytes] | None = None,
    destination: Path = Path('root'),
  ) -> None:
    self._calendar = (
      calendar.encode() if isinstance(calendar, str) else calendar
    )
    self._bodies = dict(bodies or {})
    self.destination = destination
    self.fetched: list[str] = []
    self.written: dict[str, bytes] = {}

  def fetch(self, url: str) -> bytes:
    self.fetched.append(url)
    if url.startswith(_CALENDAR_URL_PREFIX):
      return self._calendar
    # File URLs are the base joined with the percent-encoded path, so decoding
    # back recovers the site-relative path the test keys its bodies by.
    site_path = urllib.parse.unquote(url.removeprefix(_CLUB_BASE_URL))
    return self._bodies.get(site_path, b'stand-in for ' + url.encode())

  def write(self, path: Path, data: bytes) -> None:
    self.written[path.relative_to(self.destination).as_posix()] = data


def _run(
  calendar: str | bytes,
  *,
  date: datetime.date = _JUNE_29,
  bodies: Mapping[str, bytes] | None = None,
) -> _Recorder:
  """Fetch a calendar's travellers in memory; the recorder captures what
  happened.

  `recorder.written` maps each saved path (relative to the destination) to its
  bytes, in fetch order; `recorder.fetched` is every URL requested.
  """
  recorder = _Recorder(calendar, bodies=bodies)
  fetch_travellers(
    date, recorder.destination, fetch=recorder.fetch, write=recorder.write
  )
  return recorder


# --- reading a day's files ---


def test_pbn_and_html_files_are_both_fetched() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>) "
    "(<a href='../gameresults2/alpha/R260629M.htm'>R</a>)<br>"
  )

  recorder = _run(page)

  assert list(recorder.written) == [
    'gameresults2/alpha/D260629M.pbn',
    'gameresults2/alpha/R260629M.htm',
  ]


def test_pdf_hand_record_and_text_recap_are_not_fetched() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/H260629M.pdf'>H</a>) "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>)<br>"
  )

  recorder = _run(page)

  # Neither the PDF hand record nor the text recap carries a traveller.
  assert list(recorder.written) == ['gameresults2/alpha/D260629M.pbn']


def test_c_convention_html_is_fetched() -> None:
  # `C` and `R` are the two filename conventions directors use for the results
  # HTML — some post one, some the other, never both on a day. The C spelling is
  # kept just like the R one above, because the choice keys on the `.htm`
  # extension, not the prefix.
  page = _make_calendar_page(
    "<a href='../gameresults2/beta/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/beta/C260629M.htm'>C</a>)<br>"
  )

  recorder = _run(page)

  assert list(recorder.written) == ['gameresults2/beta/C260629M.htm']


def test_files_from_several_games_on_one_day_are_all_fetched() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>)<br>"
    "<a href='../gameresults2/beta/260629E.TXT'>Evening Game</a> "
    "(<a href='../gameresults2/beta/D260629E.pbn'>D</a>)<br>"
  )

  recorder = _run(page)

  assert list(recorder.written) == [
    'gameresults2/alpha/D260629M.pbn',
    'gameresults2/beta/D260629E.pbn',
  ]


@pytest.mark.parametrize(
  'entries',
  [
    pytest.param('', id='no-games'),
    pytest.param(
      "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a><br>",
      id='recap-only',
    ),
  ],
)
def test_day_with_no_traveller_files_fetches_nothing(entries: str) -> None:
  # A day may hold no games at all, or only a `.TXT` recap (some games are
  # posted no other way) — either way there is nothing to fetch.
  recorder = _run(_make_calendar_page(entries))

  assert recorder.written == {}


def test_zero_padded_day_number_is_matched() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260609M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260609M.pbn'>D</a>)<br>",
    day='09',
  )

  recorder = _run(page, date=datetime.date(2026, 6, 9))

  assert list(recorder.written) == ['gameresults2/alpha/D260609M.pbn']


# --- resolving the links the calendar writes ---


def test_wrapped_link_is_fetched_by_its_plain_path() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../downloadfile.php?filename=gameresults2/alpha/D260629M.pbn'>"
    'D</a>)<br>'
  )

  recorder = _run(page)

  # The wrapper only forces a browser download, so the file is fetched by its
  # plain path and saved under that path.
  assert list(recorder.written) == ['gameresults2/alpha/D260629M.pbn']
  assert recorder.fetched[-1] == (
    'https://paloaltobridge.org/gameresults2/alpha/D260629M.pbn'
  )


def test_relative_link_resolves_against_the_calendar_page() -> None:
  page = _make_calendar_page(
    "<a href='alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='alpha/D260629M.pbn'>D</a>)<br>"
  )

  recorder = _run(page)

  # A link with no `../` of its own hangs off the calendar's own directory, not
  # off the site root.
  assert list(recorder.written) == ['game-results/alpha/D260629M.pbn']


def test_percent_encoded_link_names_the_path_it_encodes() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D%20260629M.pbn'>D</a>)<br>"
  )

  recorder = _run(page)

  # The saved path holds the decoded character, while the file is fetched at the
  # re-encoded URL.
  assert list(recorder.written) == ['gameresults2/alpha/D 260629M.pbn']
  assert recorder.fetched[-1] == (
    'https://paloaltobridge.org/gameresults2/alpha/D%20260629M.pbn'
  )


def test_file_linked_both_ways_is_fetched_once() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>) "
    "(<a href='../downloadfile.php?filename=gameresults2/alpha/D260629M.pbn'>"
    'D</a>)<br>'
  )

  recorder = _run(page)

  # Both spellings name one file, so it is fetched and saved once.
  assert list(recorder.written) == ['gameresults2/alpha/D260629M.pbn']
  pbn_fetches = [url for url in recorder.fetched if url.endswith('.pbn')]
  assert len(pbn_fetches) == 1


def test_offsite_only_links_are_skipped() -> None:
  page = _make_calendar_page(
    "<a href='https://my.acbl.org/club-results/255752'>Evening Game</a> "
    "<a href='http://webutil.bridgebase.com/v2/tarchive.php'>(BBO)</a><br>"
  )

  recorder = _run(page)

  assert recorder.written == {}


def test_on_site_file_beside_an_offsite_link_is_fetched() -> None:
  page = _make_calendar_page(
    "<a href='https://my.acbl.org/club-results/255752'>Evening Game</a> "
    "<a href='../virtualgameresults/alpha/R260629E.htm'>(R)</a><br>"
  )

  recorder = _run(page)

  # The offsite link is skipped; the on-site file beside it is still fetched.
  assert list(recorder.written) == ['virtualgameresults/alpha/R260629E.htm']


def test_link_naming_no_file_is_skipped() -> None:
  page = _make_calendar_page("<a href='#'>Not a game</a><br>")

  recorder = _run(page)

  # A fragment-only href resolves to the calendar's own directory, which names
  # no file — it must not read as a file published in that directory.
  assert recorder.written == {}


def test_wrapped_path_climbing_above_the_site_root_is_skipped(
  caplog: pytest.LogCaptureFixture,
) -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../downloadfile.php?filename=../../../etc/passwd.pbn'>D</a>)<br>"
  )

  with caplog.at_level(logging.WARNING):
    recorder = _run(page)

  # A path escaping the site root would escape the destination too, so it is
  # dropped — and, being anomalous, logged rather than dropped silently.
  assert recorder.written == {}
  assert 'escapes the site root' in caplog.text


def test_wrapper_link_without_a_filename_is_skipped_and_logged(
  caplog: pytest.LogCaptureFixture,
) -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../downloadfile.php?other=x'>D</a>)<br>"
  )

  with caplog.at_level(logging.WARNING):
    recorder = _run(page)

  # A wrapper naming no file is anomalous — the page format may have changed —
  # so it is surfaced, not dropped silently.
  assert recorder.written == {}
  assert 'filename' in caplog.text


# --- refusing a page that isn't the index it was asked for ---


def test_page_showing_another_month_is_rejected() -> None:
  page = _make_calendar_page('', month_heading='July 2026')

  # Asking for a June date but handed July's page.
  with pytest.raises(ValueError, match='July 2026'):
    _run(page, date=datetime.date(2026, 6, 29))


def test_page_without_the_month_heading_is_rejected() -> None:
  with pytest.raises(ValueError, match='heading'):
    _run('<html><body>Down for maintenance</body></html>')


def test_missing_day_cell_is_rejected() -> None:
  page = _make_calendar_page('', day='28')

  # The page lists only day 28, so asking for June 29 finds no cell for it.
  with pytest.raises(ValueError, match='day 29'):
    _run(page, date=datetime.date(2026, 6, 29))


def test_day_number_printed_twice_is_rejected() -> None:
  # A month grid that pads its edges with the adjacent months' days prints one
  # day number in two cells, and nothing in either says which month it belongs
  # to. Refusing beats silently reading May 29's files as June 29's.
  page = (
    '<html><body>\n'
    '<h2> Game Results for June 2026 </h2>\n'
    "<table><tr class='calendar'>\n"
    "<td class='day'>\n"
    "  <div class='cdate'> 29 </div>\n"
    "  <div class='cinfo'>\n"
    "    <a href='../gameresults2/beta/260529M.TXT'>May Game</a>\n"
    "    (<a href='../gameresults2/beta/D260529M.pbn'>D</a>)<br>\n"
    '  </div>\n'
    '</td>\n'
    "<td class='day'>\n"
    "  <div class='cdate'> 29 </div>\n"
    "  <div class='cinfo'>\n"
    "    <a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a>\n"
    "    (<a href='../gameresults2/alpha/D260629M.pbn'>D</a>)<br>\n"
    '  </div>\n'
    '</td>\n'
    '</tr></table></body></html>\n'
  )

  with pytest.raises(ValueError, match='2 cells'):
    _run(page, date=datetime.date(2026, 6, 29))


# --- fetching and writing ---


def test_calendar_url_requests_the_months_page() -> None:
  recorder = _run(_make_calendar_page(''), date=datetime.date(2026, 6, 29))

  # The day parameter only marks which day the month's page highlights, so it is
  # fixed rather than tracking the date asked for.
  assert recorder.fetched[0] == (
    'https://paloaltobridge.org/game-results/?month=6&days=1&years=2026'
  )


def test_page_in_another_encoding_is_read_as_it_declares() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Café Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>)<br>",
    charset='windows-1252',
  ).encode('windows-1252')

  recorder = _run(page)

  # The page reaches the parser as bytes, so bs4 honors its declared charset.
  # UTF-8 could represent the accented name, but these bytes are not UTF-8: in
  # windows-1252 the accent is the single byte 0xE9, which is invalid UTF-8, so
  # force-decoding would raise and lose the whole day.
  assert list(recorder.written) == ['gameresults2/alpha/D260629M.pbn']


def test_a_files_written_bytes_are_the_bytes_fetched() -> None:
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/D260629M.pbn'>D</a>) "
    "(<a href='../gameresults2/alpha/R260629M.htm'>R</a>)<br>"
  )

  recorder = _run(
    page,
    bodies={
      'gameresults2/alpha/D260629M.pbn': b'% PBN 2.1',
      'gameresults2/alpha/R260629M.htm': b'<html>the traveller</html>',
    },
  )

  assert recorder.written == {
    'gameresults2/alpha/D260629M.pbn': b'% PBN 2.1',
    'gameresults2/alpha/R260629M.htm': b'<html>the traveller</html>',
  }


def test_same_filename_from_two_directors_does_not_collide() -> None:
  # Two directors regularly publish the same filename for games on one date.
  page = _make_calendar_page(
    "<a href='../gameresults2/alpha/260629M.TXT'>Morning Duplicate</a> "
    "(<a href='../gameresults2/alpha/R260629M.htm'>R</a>)<br>"
    "<a href='../gameresults2/beta/260629M.TXT'>Evening Game</a> "
    "(<a href='../gameresults2/beta/R260629M.htm'>R</a>)<br>"
  )

  recorder = _run(
    page,
    bodies={
      'gameresults2/alpha/R260629M.htm': b"alpha's",
      'gameresults2/beta/R260629M.htm': b"beta's",
    },
  )

  # Mirrored under their own directories, the like-named files sit side by side
  # with their own bytes rather than one overwriting the other.
  assert recorder.written == {
    'gameresults2/alpha/R260629M.htm': b"alpha's",
    'gameresults2/beta/R260629M.htm': b"beta's",
  }

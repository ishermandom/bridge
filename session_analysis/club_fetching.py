# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Fetch published game-result files from the Palo Alto Bridge Center website.

The club publishes a game's results as a small set of files: a PBN carrying the
deals and the full traveller, and BridgeComposer HTML carrying the same material
rendered for reading. Which of those exist varies by the director who uploaded
them, and each director uploads into a directory of their own, so neither the
directory nor the filename follows from the date. The month calendar at
`/game-results/` is the only reliable index — it lists each day's games with
links to the files each one has — so which files exist is read from the calendar
rather than derived from the date.

`fetch_travellers` is the entry point: it reads the calendar for a date and
downloads that day's PBN and HTML files, mirroring the site's own directory
layout beneath a destination. A downloaded file identifies the game it belongs
to by its own contents, not by the calendar's label or its path, so matching a
file to a session is left to whatever reads the files afterward.
"""

import datetime
import logging
import posixpath
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

import bs4

logger = logging.getLogger(__name__)

_CLUB_BASE_URL = 'https://paloaltobridge.org/'
_CALENDAR_PATH = 'game-results/'
_CALENDAR_URL = urllib.parse.urljoin(_CLUB_BASE_URL, _CALENDAR_PATH)

# The calendar renders a whole month at a time, and its day parameter only marks
# which day to highlight, so any day in the month selects the same page.
_CALENDAR_HIGHLIGHTED_DAY = 1

# The heading the calendar prints above the month it is showing, e.g. "Game
# Results for June 2026". Month and year are captured apart so that whatever
# separates them — an ordinary space, or the non-breaking one this site's markup
# uses elsewhere — cannot decide whether the heading is recognized.
_MONTH_HEADING_PATTERN = re.compile(
  r'Game Results for\s+(?P<month>\w+)\s+(?P<year>\d{4})'
)

# Some links reach a file through a wrapper that carries the real path in a
# query parameter instead of in the path itself, e.g.
# `downloadfile.php?filename=gameresults2/watson/D260629M.pbn`. The wrapper only
# forces a browser to download rather than display, so the underlying path can
# be fetched directly.
_DOWNLOAD_WRAPPER_NAME = 'downloadfile.php'
_DOWNLOAD_WRAPPER_PARAMETER = 'filename'

# The extensions worth downloading: a PBN and the two spellings of the results
# HTML. Both carry the full traveller. Every other published file — the
# hand-record PDFs and the plain-text recap — carries no traveller.
_TRAVELLER_FILE_EXTENSIONS = frozenset({'.pbn', '.htm', '.html'})

_FETCH_TIMEOUT_SECONDS = 30
_USER_AGENT = 'bridge-session-analysis (personal scoresheet digitization)'


def _traveller_file(*, href: str, page_url: str) -> str | None:
  """The site-relative path of the traveller file a link points at, or `None`.

  `None` covers every link that is not a PBN or HTML results file: an offsite
  link, a fragment or empty href, a link to a directory, or an on-site file we
  do not keep (the `.TXT` recap, the `.pdf` hand record).

  Args:
    href: a link's `href` exactly as the calendar wrote it, which may be
       relative — e.g. `../gameresults2/watson/D260629M.pbn`, or a wrapped
      `../downloadfile.php?filename=gameresults2/watson/D260629M.pbn`.
    page_url: the absolute URL of the calendar page the `href` was read from —
      e.g. `https://paloaltobridge.org/game-results/?month=6&days=1&years=2026`.
      A relative `href` means what it means on that page, so it resolves against
      this rather than against the site root.
  """
  page = urllib.parse.urlsplit(page_url)
  target = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, href))

  # Offsite links: the online games link to their host, not to files here.
  if (target.scheme, target.netloc) != (page.scheme, page.netloc):
    return None

  # Percent-decoded, because this path doubles as a filename on disk and the
  # wrapper hands over its own copy already decoded — leaving the direct
  # spelling encoded would give one file two identities.
  path = urllib.parse.unquote(target.path).lstrip('/')
  if posixpath.basename(path) == _DOWNLOAD_WRAPPER_NAME:
    wrapped = urllib.parse.parse_qs(target.query).get(
      _DOWNLOAD_WRAPPER_PARAMETER
    )
    if not wrapped:
      # Every wrapper link on this site names a file; one that does not is a
      # sign the page format changed, so it is surfaced rather than dropped
      # silently.
      logger.warning(
        f'skipping download wrapper link with no '
        f'{_DOWNLOAD_WRAPPER_PARAMETER!r} parameter: {href!r}'
      )
      return None
    path = wrapped[0].lstrip('/')

  # A link naming no file of its own: a fragment-only or empty href resolves to
  # the directory the calendar sits in, and a link to a directory names no file.
  if not posixpath.basename(path):
    return None

  normalized = posixpath.normpath(path)
  if normalized == '..' or normalized.startswith('../'):
    # A path climbing above the site root — which this site has not been
    # observed to emit, and which would escape the download destination when
    # saved. Anomalous rather than routine, so it is surfaced.
    logger.warning(f'skipping link whose path escapes the site root: {href!r}')
    return None

  extension = posixpath.splitext(normalized)[1].lower()
  return normalized if extension in _TRAVELLER_FILE_EXTENSIONS else None


def _day_cells(soup: bs4.BeautifulSoup, day: int) -> Sequence[bs4.Tag]:
  """The calendar cells for a given day number — normally exactly one.

  The month grid renders each day as a `<div class='cdate'>` holding the day
  number, immediately followed by a sibling `<div class='cinfo'>` holding that
  day's games:

  ```html
  <td class='day'>
    <div class='cdate'> 29 </div>
    <div class='cinfo'>
      <a href='../gameresults2/watson/260629M.TXT'>Palo Alto Duplicate</a>
      (<a href='../gameresults2/watson/D260629M.pbn'>D</a>)
      (<a href='../gameresults2/watson/R260629M.htm'>R</a>)
    </div>
  </td>
  ```

  This returns the `cinfo` cell for every `cdate` matching `day`.

  Returning a list, rather than the single cell, is defensive against a layout
  this site is not observed to use: a grid that padded its first and last rows
  with the adjacent months' days would print some day numbers twice, with
  nothing in a cell saying which month it belongs to. Every match lets the
  caller refuse such an ambiguous page instead of reading one of two cells as
  the requested day. On this site the calendar shows a single unpadded month, so
  the list holds one cell.

  Args:
    soup: the parsed calendar page.
    day: the day of the month to find, as a number (1 to 31).
  """
  cells = []
  for day_number in soup.find_all('div', class_='cdate'):
    printed = day_number.get_text(strip=True)
    # Compared numerically so a zero-padded day would still match, though this
    # site prints the day unpadded.
    if not printed.isdigit() or int(printed) != day:
      continue
    cell = day_number.find_next_sibling('div', class_='cinfo')
    if isinstance(cell, bs4.Tag):
      cells.append(cell)
  return cells


def _shown_month(soup: bs4.BeautifulSoup) -> str | None:
  """The "Month Year" the calendar's heading names, or `None` if it has none.

  Reads only what the page says it is showing; whether that is the month asked
  for is the caller's decision. Defensive: the calendar honors the requested
  month, so this differs from the request only if the server ever ignored the
  query parameters and served a different month.

  Args:
    soup: the parsed calendar page.
  """
  heading = _MONTH_HEADING_PATTERN.search(soup.get_text())
  if not heading:
    return None
  return f'{heading.group("month")} {heading.group("year")}'


def _traveller_file_paths(
  page: str | bytes, date: datetime.date, page_url: str = _CALENDAR_URL
) -> Sequence[str]:
  """The site-relative paths of `date`'s traveller files on a calendar page.

  The pure-logic core behind `fetch_travellers`, split out so it can be tested
  without the network. A file linked twice — directly and through the wrapper —
  appears once; order follows the calendar.

  Args:
    page: the calendar HTML, decoded or as the bytes it was fetched as — bs4
      reads the encoding the page declares, which need not be UTF-8.
    date: the date whose files to read.
    page_url: the absolute URL the page was fetched from; the calendar's
      relative links resolve against it.

  Raises:
    ValueError: if the page is not the index it was asked for — no recognizable
      heading, a month other than `date`'s, or that day given anything but
      exactly one cell (an ambiguity a padded grid could introduce). Reading a
      day number out of such a page would yield some other date's files.
  """
  soup = bs4.BeautifulSoup(page, 'html.parser')

  shown_month = _shown_month(soup)
  requested_month = f'{date:%B %Y}'
  if shown_month is None:
    raise ValueError(
      'calendar page has no "Game Results for <month year>" heading'
    )
  if shown_month != requested_month:
    raise ValueError(
      f'calendar shows {shown_month!r}, but {requested_month!r} was requested'
    )

  cells = _day_cells(soup, date.day)
  if not cells:
    raise ValueError(
      f'calendar for {requested_month} has no cell for day {date.day}'
    )
  if len(cells) > 1:
    raise ValueError(
      f'calendar for {requested_month} gives day {date.day} {len(cells)} '
      'cells, and a day number belonging to an adjacent month reads the same '
      'as the requested one'
    )

  found = []
  for link in cells[0].find_all('a'):
    # str() narrows bs4's str-or-list attribute type; href is single-valued.
    traveller_path = _traveller_file(
      href=str(link.get('href', '')), page_url=page_url
    )
    if traveller_path:
      found.append(traveller_path)
  # A day with no traveller files yields none — an ordinary result, whether the
  # day held no games or only recaps. `dict.fromkeys` dedups while keeping
  # order.
  return tuple(dict.fromkeys(found))


def _calendar_url(date: datetime.date) -> str:
  """The calendar page URL for the month containing `date`.

  Args:
    date: any date in the month to show; its day only sets which cell the
      calendar highlights, not which month it renders.
  """
  query = urllib.parse.urlencode(
    {
      'month': date.month,
      'days': _CALENDAR_HIGHLIGHTED_DAY,
      'years': date.year,
    }
  )
  # `_replace` is a NamedTuple's public method (underscored only to avoid
  # clashing with field names); it swaps in the query and keeps the rest.
  split = urllib.parse.urlsplit(_CALENDAR_URL)
  return urllib.parse.urlunsplit(split._replace(query=query))


def _fetch_url(url: str) -> bytes:
  """Retrieve a URL's raw bytes, raising on anything but success.

  Args:
    url: the absolute URL to fetch.
  """
  request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
  with urllib.request.urlopen(
    request, timeout=_FETCH_TIMEOUT_SECONDS
  ) as response:
    data: bytes = response.read()
    return data


def _write_file(destination: Path, data: bytes) -> None:
  """Write `data` to `destination`, creating any missing parent directories.

  The one place this module touches disk, kept behind a seam so tests can supply
  an in-memory writer instead.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  destination.write_bytes(data)


def fetch_travellers(
  date: datetime.date,
  destination: Path,
  *,
  fetch: Callable[[str], bytes] = _fetch_url,
  write: Callable[[Path, bytes], None] = _write_file,
) -> Sequence[Path]:
  """Download every PBN and HTML results file the club published for `date`.

  Reads the month calendar, finds the day, and saves each of that day's
  traveller files beneath `destination` at its own site-relative path. Mirroring
  the site's directories rather than flattening is what keeps like-named files
  apart: the same filename recurs across directories — a game's in-person and
  online copies live under `gameresults2/` and `virtualgameresults/`, and each
  director publishes into a directory of their own — so flattening to bare names
  would overwrite one file with another. A file linked through the download
  wrapper is fetched by its plain path, since the wrapper only forces a browser
  to save rather than display.

  Args:
    date: the date whose files to fetch.
    destination: the root directory the files are saved beneath, each at its own
      site-relative path.
    fetch: retrieves a URL's bytes; injectable so tests need no network.
    write: writes bytes to a path; injectable so tests need no disk.

  Returns:
    The path each file was written to, in the order the calendar lists them.
  """
  calendar_url = _calendar_url(date)
  traveller_paths = _traveller_file_paths(
    fetch(calendar_url), date, calendar_url
  )

  written = []
  for traveller_path in traveller_paths:
    file_url = urllib.parse.urljoin(
      _CLUB_BASE_URL, urllib.parse.quote(traveller_path)
    )
    path = destination / traveller_path
    write(path, fetch(file_url))
    written.append(path)
  return tuple(written)

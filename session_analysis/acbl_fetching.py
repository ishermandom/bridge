# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Fetch a player's official game records from ACBL Live.

ACBL publishes results on two public surfaces, both keyed by an ACBL player
number: tournaments at `https://live.acbl.org/player-results/<number>` and club
games at `https://my.acbl.org/club-results/my-results/<number>`.
`fetch_tournament_travellers` and `fetch_club_travellers` are the entry points —
each reads the player's index for its surface, finds the sessions played on a
date, and downloads each session's traveller.

The two surfaces work the same way, so they share their machinery and differ
only in a handful of per-site details (the `_Surface` values below): the same
means of clearing Cloudflare serves both, and the same walk reads a dated table
of game links and saves each linked page. Each entry point runs its own browser,
so a run that fetches both surfaces clears two challenges.

Two facts shape the design:

- **Cloudflare guards every ACBL page.** A plain HTTP client can't get past its
  challenge, so every page comes through `cloudflare_fetching`'s browser. That
  browser sits behind the same injectable seam `club_fetching` uses, so the
  parsing logic stays testable without a browser or the network.
- **The capture is the page's own HTML.** A traveller's data lives in the page —
  a tournament's board data in HTML tables, a club page's additionally in a `var
  data = {...}` blob — so the saved artifact is that HTML, lean by construction
  since driving the page ourselves avoids the asset bundle a browser's "save
  page" drags in. Turning a capture into a traveller, including parsing a club
  page's JSON blob, is left to a later parser.
"""

import contextlib
import datetime
import logging
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import bs4

from session_analysis import capture_urls, cloudflare_fetching

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Surface:
  """The per-site details that distinguish one ACBL results surface's fetch.

  Attributes:
    base_url: the site the surface lives on.
    index_path: joined with a player number to form the results-index URL.
    table_id: the id of the DataTables table listing the player's sessions.
    date_format: the `strptime` format of the table's first (date) column.
    link_prefix: a traveller link's site-relative path starts with this,
    link_suffix: and ends with this (empty when it has no fixed suffix).
    has_section_pages: whether a traveller shows one section of the session at
      a time, so that the player's own section may need fetching apart from
      the page the index links to.
  """

  base_url: str
  index_path: str
  table_id: str
  date_format: str
  link_prefix: str
  link_suffix: str
  has_section_pages: bool


# Tournaments: the date reads `MM/DD/YYYY` and a session's traveller is the
# `.../summary` view under `event/<id>/<session>/<n>/`, which shows one section
# at a time.
_TOURNAMENTS = _Surface(
  base_url='https://live.acbl.org/',
  index_path='player-results/',
  table_id='events',
  date_format='%m/%d/%Y',
  link_prefix='event/',
  link_suffix='/summary',
  has_section_pages=True,
)

# Club games: the date reads `YYYY-MM-DD` and a game's traveller is a
# `club-results/details/<id>` page.
_CLUBS = _Surface(
  base_url='https://my.acbl.org/',
  index_path='club-results/my-results/',
  table_id='results-table',
  date_format='%Y-%m-%d',
  link_prefix='club-results/details/',
  link_suffix='',
  has_section_pages=False,
)

# The query parameter a tournament summary takes to show a section other than
# its first, as in `.../summary?section=B`.
_SECTION_PARAMETER = 'section'


@dataclass(frozen=True)
class _Session:
  """One session listed on a player's results index.

  Attributes:
    date: the day the session was played.
    traveller_path: the traveller's site-relative path, e.g.
      `event/2606319/27OP/2/summary` or `club-results/details/1484015`.
    label: a human-readable description — the columns after the date — carried
      only for logging what was fetched.
  """

  date: datetime.date
  traveller_path: str
  label: str


@dataclass(frozen=True)
class _Page:
  """A fetched page, beside the absolute URL it was fetched from."""

  url: str
  body: bytes


def _index_url(surface: _Surface, player_number: str) -> str:
  """The results-index URL for a player on `surface`.

  Args:
    surface: the results surface to read.
    player_number: the ACBL player number whose results to read.
  """
  return urllib.parse.urljoin(
    surface.base_url, surface.index_path + urllib.parse.quote(player_number)
  )


def _traveller_path(href: str, page_url: str, surface: _Surface) -> str | None:
  """The site-relative path of the traveller a link points at, or `None`.

  `None` for any link that is not an on-site traveller for `surface`. A row
  links to several of a session's views, so most of a row's links are not
  travellers — this is the quiet test used to pick the traveller out, not an
  anomaly to report.

  Args:
    href: a link's `href`, which may be relative.
    page_url: the absolute URL of the index page, for resolving `href`.
    surface: the results surface, whose link shape the path must match.
  """
  page = urllib.parse.urlsplit(page_url)
  target = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, href))
  if (target.scheme, target.netloc) != (page.scheme, page.netloc):
    return None
  path = target.path.lstrip('/')
  if not (
    path.startswith(surface.link_prefix) and path.endswith(surface.link_suffix)
  ):
    return None
  return path


def _row_session(
  row: bs4.Tag, page_url: str, surface: _Surface
) -> _Session | None:
  """The session a results-index row describes, or `None` if it is not one.

  The traveller link is found by its href rather than its class: the raw markup
  can give an anchor two `class` attributes, which HTML parsers collapse
  unpredictably, but its href is unambiguous. A row with no traveller link is
  not a session (a header or a spacer) and yields `None` quietly; a row that has
  one but whose date will not parse is anomalous and is logged.

  Args:
    row: a `<tr>` from the index table's body.
    page_url: the absolute URL of the index page, for resolving links.
    surface: the results surface, whose link shape and date format apply.
  """
  traveller_path = None
  for link in row.find_all('a'):
    traveller_path = _traveller_path(
      str(link.get('href', '')), page_url, surface
    )
    if traveller_path:
      break
  if not traveller_path:
    return None

  cells = [cell.get_text(strip=True) for cell in row.find_all('td')]
  if not cells:
    return None
  try:
    date = datetime.datetime.strptime(cells[0], surface.date_format).date()
  except ValueError:
    logger.warning(
      f'skipping a session row whose date cell {cells[0]!r} is not '
      f'{surface.date_format!r}'
    )
    return None

  # The columns after the date describe the session (its tournament or club,
  # event, and start time); join whichever are present into a label for the log.
  label = ' — '.join(cell for cell in cells[1:4] if cell)
  return _Session(date=date, traveller_path=traveller_path, label=label)


def _sessions(
  page: str | bytes, page_url: str, surface: _Surface
) -> Sequence[_Session]:
  """Every session listed on a player's index page for `surface`.

  The pure-logic core behind the walk, split out so it can be tested without a
  browser.

  Args:
    page: the index HTML, decoded or as fetched bytes.
    page_url: the absolute URL the page was fetched from, for resolving links.
    surface: the results surface being read.

  Raises:
    ValueError: if the page has no index table — it is not the index it was
      taken for, and reading sessions out of it would be meaningless.
  """
  soup = bs4.BeautifulSoup(page, 'html.parser')
  table = soup.find('table', id=surface.table_id)
  if not isinstance(table, bs4.Tag):
    raise ValueError(f'results page has no <table id={surface.table_id!r}>')

  body = table.find('tbody')
  container = body if isinstance(body, bs4.Tag) else table
  rows = container.find_all('tr')
  sessions = tuple(
    filter(None, (_row_session(row, page_url, surface) for row in rows))
  )
  if rows and not sessions:
    # Rows present but none held a traveller link: the layout the parser keys on
    # has probably changed, and returning empty would hide that.
    logger.warning(
      f'{surface.table_id!r} table has {len(rows)} row(s) but none held a '
      'traveller link; the page layout may have changed'
    )
  return sessions


def _player_section(
  summary: _Page, player_number: str, fetch: Callable[[str], bytes]
) -> _Page:
  """The section of a tournament session that the player's pair sat in.

  A session played in several sections publishes each one's results on its own
  page, and the index links only to the first. travellers.md `#acquisition` says
  why only the player's section is kept.

  Args:
    summary: the summary page the index links to.
    player_number: the ACBL player number whose section to find.
    fetch: retrieves a URL's bytes, for the sections `summary` does not show.

  Returns:
    `summary` itself when it shows the player's section or offers no other, as
    every single-section session's page does. When several sections are offered
    and none lists the player, `summary` too, with a warning: the session is
    still captured, and reconciliation reports the missing row.
  """
  soup = bs4.BeautifulSoup(summary.body, 'html.parser')
  if _lists_player(soup, player_number):
    return summary

  # A single-section session's page has no section picker at all.
  pickers = soup.select('a.section-select')
  shown = {
    picker.get_text(strip=True)
    for picker in soup.select('a.section-select.selected')
  }
  for picker in pickers:
    section = picker.get_text(strip=True)
    if section in shown:
      continue
    url = _section_url(summary.url, section)
    body = fetch(url)
    if _lists_player(bs4.BeautifulSoup(body, 'html.parser'), player_number):
      return _Page(url, body)

  if pickers:
    logger.warning(
      f'no section of {summary.url} lists player {player_number}; saving the '
      'section the page opens on'
    )
  return summary


def _lists_player(soup: bs4.BeautifulSoup, player_number: str) -> bool:
  """Whether the section a summary page shows lists `player_number`'s pair.

  Read from the section's own recap table rather than the whole page: the
  event-wide leaderboard above it lists every section's pairs on every section's
  page.
  """
  selector = f'table.recaps-table [data-acbl="{player_number}"]'
  return soup.select_one(selector) is not None


def _section_url(summary_url: str, section: str) -> str:
  """The URL of `section`'s page of the summary at `summary_url`."""
  query = urllib.parse.urlencode({_SECTION_PARAMETER: section})
  return urllib.parse.urlsplit(summary_url)._replace(query=query).geturl()


def _capture_path(destination: Path, traveller_url: str) -> Path:
  """Where a traveller's HTML is saved beneath `destination`.

  The capture sits at the traveller's own host-qualified path, so captures from
  the two ACBL hosts — and any basename that recurs across sessions, like
  `summary` — cannot collide.

  Args:
    destination: the root directory captures are saved beneath.
    traveller_url: the absolute URL the page was fetched from.
  """
  parts = urllib.parse.urlsplit(traveller_url)
  base = destination / parts.netloc / parts.path.lstrip('/')

  # A section's page shares its path with the session's first section, and
  # differs only in the query, so the section goes into the name.
  sections = urllib.parse.parse_qs(parts.query).get(_SECTION_PARAMETER)
  if sections:
    base = base.with_name(f'{base.name}-section-{sections[0]}')
  return base.with_suffix('.html')


def _write_file(destination: Path, data: bytes) -> None:
  """Write `data` to `destination`, creating any missing parent directories.

  The one place this module touches disk, kept behind a seam so tests can supply
  an in-memory writer instead.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  destination.write_bytes(data)


def fetch_tournament_travellers(
  player_number: str,
  date: datetime.date,
  destination: Path,
  *,
  fetch: Callable[[str], bytes] | None = None,
  write: Callable[[Path, bytes], None] = _write_file,
) -> Sequence[Path]:
  """Download a player's ACBL Live tournament travellers for `date`.

  Reads the player's public tournament index
  (`live.acbl.org/player-results/<number>`), keeps the sessions played on
  `date`, and saves each one's summary page beneath `destination` — for a
  session played in several sections, the page of the player's own section. A
  typical tournament day plays more than one session, so several travellers can
  come back for one date; a day the player did not play comes back empty.

  Args:
    player_number: the ACBL player number whose results to fetch.
    date: the date whose travellers to download.
    destination: this surface's own capture directory; each page is
      saved beneath it at that page's own host-qualified path.
    fetch: retrieves a URL's bytes; defaults to a browser that clears
      Cloudflare, and is injectable so tests need no browser or network.
    write: writes bytes to a path; injectable so tests need no disk. It
      receives two files per capture: the page itself, and the sidecar
      naming the URL that page came from.

  Returns:
    The path each traveller was saved to, in the order the index lists them.
  """
  return _fetch_travellers(
    _TOURNAMENTS, player_number, date, destination, fetch=fetch, write=write
  )


def fetch_club_travellers(
  player_number: str,
  date: datetime.date,
  destination: Path,
  *,
  fetch: Callable[[str], bytes] | None = None,
  write: Callable[[Path, bytes], None] = _write_file,
) -> Sequence[Path]:
  """Download a player's ACBL club-game travellers for `date`.

  Reads the player's public club index
  (`my.acbl.org/club-results/my-results/<number>`), keeps the games played on
  `date`, and saves each one's detail page beneath `destination`. These ACBL
  club records corroborate the Palo Alto club site's own copies, which
  `club_fetching` fetches.

  Args:
    player_number: the ACBL player number whose results to fetch.
    date: the date whose travellers to download.
    destination: this surface's own capture directory; each page is
      saved beneath it at that page's own host-qualified path.
    fetch: retrieves a URL's bytes; defaults to a browser that clears
      Cloudflare, and is injectable so tests need no browser or network.
    write: writes bytes to a path; injectable so tests need no disk. It
      receives two files per capture: the page itself, and the sidecar
      naming the URL that page came from.

  Returns:
    The path each traveller was saved to, in the order the index lists them.
  """
  return _fetch_travellers(
    _CLUBS, player_number, date, destination, fetch=fetch, write=write
  )


def _fetch_travellers(
  surface: _Surface,
  player_number: str,
  date: datetime.date,
  destination: Path,
  *,
  fetch: Callable[[str], bytes] | None,
  write: Callable[[Path, bytes], None],
) -> Sequence[Path]:
  """Read `surface`'s index, keep `date`'s sessions, and save each traveller.

  Shared by both entry points. When `fetch` is `None` a browser is launched for
  the run and quit after; an injected `fetch` is used as given.
  """
  with contextlib.ExitStack() as stack:
    if fetch is None:
      fetch = stack.enter_context(cloudflare_fetching.BrowserFetcher()).fetch

    index_url = _index_url(surface, player_number)
    sessions = _sessions(fetch(index_url), index_url, surface)
    day_sessions = [session for session in sessions if session.date == date]
    logger.info(
      f'{len(day_sessions)} session(s) for player {player_number} on '
      f'{date:%Y-%m-%d} at {surface.base_url}'
    )

    written = []
    for session in day_sessions:
      logger.info(f'fetching {session.label or session.traveller_path}')
      traveller_url = urllib.parse.urljoin(
        surface.base_url, session.traveller_path
      )
      page = _Page(traveller_url, fetch(traveller_url))
      if surface.has_section_pages:
        page = _player_section(page, player_number, fetch)

      path = _capture_path(destination, page.url)
      write(path, page.body)
      write(
        capture_urls.sidecar_for(path),
        capture_urls.sidecar_contents(page.url),
      )
      written.append(path)
    return tuple(written)

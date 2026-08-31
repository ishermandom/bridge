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
headless browser clears Cloudflare for both, and the same walk reads a dated
table of game links and saves each linked page.

Two facts shape the design:

- **Cloudflare guards every ACBL page.** Both surfaces sit behind a Cloudflare
  "managed challenge" — JavaScript a browser must run before the real content is
  served — which a plain HTTP client cannot satisfy. Fetching therefore drives a
  real headless browser (Playwright), kept behind the same injectable seam
  `club_fetching` uses so the parsing logic stays testable without a browser or
  the network.
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
from playwright.sync_api import (
  Browser,
  Page,
  Playwright,
  sync_playwright,
)
from playwright.sync_api import (
  Error as PlaywrightError,
)

from session_analysis import capture_urls

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
  """

  base_url: str
  index_path: str
  table_id: str
  date_format: str
  link_prefix: str
  link_suffix: str


# Tournaments: the date reads `MM/DD/YYYY` and a session's traveller is the
# `.../summary` view under `event/<id>/<session>/<n>/`.
_TOURNAMENTS = _Surface(
  base_url='https://live.acbl.org/',
  index_path='player-results/',
  table_id='events',
  date_format='%m/%d/%Y',
  link_prefix='event/',
  link_suffix='/summary',
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
)

# Cloudflare serves this interstitial title until the challenge is solved.
_CHALLENGE_TITLE = 'Just a moment'

# Read the current page's own bytes through the browser, reusing its
# Cloudflare-cleared session. Going back to the server rather than serializing
# the live DOM keeps the capture deterministic and, for a paginated index,
# returns every row rather than the one page DataTables leaves mounted.
_PAGE_SOURCE_SCRIPT = (
  "() => fetch(window.location.href, {credentials: 'include'})"
  '.then((response) => response.text())'
)

_NAVIGATION_TIMEOUT_MS = 45_000
_CHALLENGE_TIMEOUT_MS = 30_000
_CHALLENGE_POLL_MS = 1_000
_CHALLENGE_ATTEMPTS = 3

# How much of a fetched body to scan for the challenge interstitial's title: the
# head, so a real page that happens to mention the phrase deep in its content is
# not mistaken for a challenge.
_CHALLENGE_HEAD_BYTES = 4096


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
  return base.with_suffix('.html')


def _write_file(destination: Path, data: bytes) -> None:
  """Write `data` to `destination`, creating any missing parent directories.

  The one place this module touches disk, kept behind a seam so tests can supply
  an in-memory writer instead.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  destination.write_bytes(data)


class _BrowserFetcher:
  """A `fetch(url) -> bytes` backed by a headless browser, the seam's default.

  See the module docstring for why a real browser is needed. Lifecycle notes:
  One browser is launched and reused across a run — the class is a context
  manager — so Cloudflare's challenge is solved once and its clearance carries
  to later fetches.
  """

  def __init__(self) -> None:
    self._playwright: Playwright | None = None
    self._browser: Browser | None = None
    self._page: Page | None = None

  def __enter__(self) -> '_BrowserFetcher':
    return self

  def __exit__(self, *exception: object) -> None:
    self.close()

  def fetch(self, url: str) -> bytes:
    """Fetch a URL's rendered HTML, clearing the challenge if it is served.

    The challenge usually clears in a few seconds, but a burst of requests can
    draw a harder one, and clearing it navigates the page. An attempt that does
    not clear, or whose read is torn down by that navigation, is retried a few
    times before giving up.
    """
    page = self._ensure_page()
    for _ in range(_CHALLENGE_ATTEMPTS):
      try:
        page.goto(
          url, wait_until='domcontentloaded', timeout=_NAVIGATION_TIMEOUT_MS
        )
        if not self._challenge_cleared(page):
          logger.warning(f'Cloudflare challenge did not clear; retrying: {url}')
          continue
        # Clearing the challenge navigates to the real page; wait for that to
        # finish so the in-page read is not run against a context the navigation
        # is about to tear down.
        page.wait_for_load_state('load', timeout=_NAVIGATION_TIMEOUT_MS)
        body = str(page.evaluate(_PAGE_SOURCE_SCRIPT)).encode('utf-8')
        # The in-page read is itself a fresh request that can draw a challenge
        # even after the DOM cleared; that interstitial names itself in its
        # head. Retry rather than save the challenge as the capture.
        if _CHALLENGE_TITLE.encode() in body[:_CHALLENGE_HEAD_BYTES]:
          logger.warning(
            f'fetched body is a Cloudflare challenge; retrying: {url}'
          )
          continue
        return body
      except PlaywrightError as error:
        logger.warning(f'fetch attempt failed ({error}); retrying: {url}')
    raise RuntimeError(
      f'could not fetch past Cloudflare after {_CHALLENGE_ATTEMPTS} '
      f'attempts: {url}'
    )

  def _challenge_cleared(self, page: Page) -> bool:
    """Poll until Cloudflare's interstitial gives way, or the wait runs out.

    Returns whether the real page appeared. The challenge holds `document.title`
    at its interstitial value until its JavaScript solves it and navigates to
    the page asked for, so this polls the title across those navigations rather
    than watching one execution context, which the challenge's own reload would
    tear down.
    """
    waited_ms = 0
    while _CHALLENGE_TITLE in page.title():
      if waited_ms >= _CHALLENGE_TIMEOUT_MS:
        return False
      page.wait_for_timeout(_CHALLENGE_POLL_MS)
      waited_ms += _CHALLENGE_POLL_MS
    return True

  def _ensure_page(self) -> Page:
    """Launch the browser on first use and return its page.

    Cloudflare's managed challenge only clears for a browser that passes three
    checks, so the launch is deliberate about all three:

    - the full Chromium, via the `chromium` channel — the default headless
      browser is the lighter "headless shell", which the challenge flags;
    - `navigator.webdriver` hidden — Playwright offers no setting for this, so
      the Chromium flag is the accepted way, and it is load-bearing (with
      webdriver visible the challenge never clears);
    - a user agent without the `HeadlessChrome` marker the challenge blocks, its
      version taken from the running browser so it never drifts.
    """
    if self._page:
      return self._page

    # Assign each handle as it is created, not all at the end, so a failure
    # partway through still leaves `close` able to shut down what did start.
    playwright = sync_playwright().start()
    self._playwright = playwright
    browser = playwright.chromium.launch(
      headless=True,
      channel='chromium',
      args=['--disable-blink-features=AutomationControlled'],
    )
    self._browser = browser

    major_version = browser.version.split('.')[0]
    user_agent = (
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      f'(KHTML, like Gecko) Chrome/{major_version}.0.0.0 Safari/537.36'
    )
    context = browser.new_context(
      user_agent=user_agent,
      viewport={'width': 1280, 'height': 900},
      locale='en-US',
    )
    page = context.new_page()
    self._page = page
    return page

  def close(self) -> None:
    """Shut the browser and Playwright down; safe to call more than once."""
    if self._browser:
      self._browser.close()
      self._browser = None
    if self._playwright:
      self._playwright.stop()
      self._playwright = None
    self._page = None


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
  `date`, and saves each one's summary page beneath `destination`. A typical
  tournament day plays more than one session, so several travellers can come
  back for one date; a day the player did not play comes back empty.

  Args:
    player_number: the ACBL player number whose results to fetch.
    date: the date whose travellers to download.
    destination: this surface's own capture directory; each page is
      saved beneath it at that page's own host-qualified path.
    fetch: retrieves a URL's bytes; defaults to a headless browser that clears
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
    fetch: retrieves a URL's bytes; defaults to a headless browser that clears
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

  Shared by both entry points. When `fetch` is `None` a headless browser is
  launched for the run and closed after; an injected `fetch` is used as given.
  """
  with contextlib.ExitStack() as stack:
    if fetch is None:
      fetch = stack.enter_context(_BrowserFetcher()).fetch

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
      path = _capture_path(destination, traveller_url)
      write(path, fetch(traveller_url))
      write(
        capture_urls.sidecar_for(path),
        capture_urls.sidecar_contents(traveller_url),
      )
      written.append(path)
    return tuple(written)

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

- **Cloudflare guards every ACBL page, and watches for a debugger.** Both
  surfaces sit behind a "managed challenge" — JavaScript a browser must run
  before the real content is served — which a plain HTTP client cannot satisfy.
  The challenge also refuses to clear at all while a debugger is attached: it
  puts a getter-instrumented payload through every `console` method and watches
  for the side effects of something serializing them. So a browser is launched
  and left alone to meet the challenge, and the debugger attaches only
  afterwards, to read the page. Headless is refused outright, whatever else is
  true, so the browser is a visible one in this account's own desktop session.
  All of it sits behind the same injectable seam `club_fetching` uses, so the
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
import json
import logging
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import bs4
from playwright.sync_api import (
  Error as PlaywrightError,
)
from playwright.sync_api import Playwright, sync_playwright

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

# How much of a fetched body to scan for the interstitial's title: the head, so
# a real page that happens to mention the phrase deep in its content is not
# mistaken for a challenge.
_CHALLENGE_HEAD_BYTES = 4096

# Read the current page's own bytes through the browser, reusing its
# Cloudflare-cleared session. Going back to the server rather than serializing
# the live DOM keeps the capture deterministic and, for a paginated index,
# returns every row rather than the one page DataTables leaves mounted.
_PAGE_SOURCE_SCRIPT = (
  "() => fetch(window.location.href, {credentials: 'include'})"
  '.then((response) => response.text())'
)

_BROWSER_START_TIMEOUT_SECONDS = 30
_CHALLENGE_TIMEOUT_SECONDS = 60
_CHALLENGE_ATTEMPTS = 3
_POLL_SECONDS = 1
_DEVTOOLS_TIMEOUT_SECONDS = 20


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


def _browser_app(playwright: Playwright) -> Path:
  """The application bundle to launch: the Chromium Playwright brings along.

  Using the browser the project already depends on, rather than whatever the
  machine happens to have installed, keeps the version pinned alongside the code
  and asks nothing of the machine. `open` takes a bundle, which sits three
  levels above the executable Playwright names.
  """
  return Path(playwright.chromium.executable_path).parents[2]


def _devtools_request(port: int, path: str, *, decode: bool = True) -> object:
  """Call a browser's DevTools HTTP endpoint, attaching no debugger to a page.

  Args:
    port: the browser's debugging port.
    path: the endpoint path, query string included.
    decode: whether the endpoint answers JSON; `/json/close/<id>` answers prose.
  """
  # `/json/new` is the one endpoint that insists on `PUT`.
  method = 'PUT' if path.startswith('/json/new') else 'GET'
  request = urllib.request.Request(
    f'http://127.0.0.1:{port}{path}', method=method
  )
  with urllib.request.urlopen(
    request, timeout=_DEVTOOLS_TIMEOUT_SECONDS
  ) as response:
    body = response.read()
  return json.loads(body) if decode else None


def _free_port() -> int:
  """A port nothing is listening on, for the browser's debugging endpoint.

  Asking the kernel for one beats a fixed number, which would collide with a
  browser the person at the keyboard is already debugging.
  """
  with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port: int = probe.getsockname()[1]
    return port


def _write_file(destination: Path, data: bytes) -> None:
  """Write `data` to `destination`, creating any missing parent directories.

  The one place this module touches disk, kept behind a seam so tests can supply
  an in-memory writer instead.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  destination.write_bytes(data)


class _Browser(Protocol):
  """What a fetch needs a browser to do, apart from deciding when to do it.

  Drawing the line here keeps the half that cannot run without a real browser —
  launching one, calling its debugging endpoints, attaching to read a page —
  apart from the half that decides what to do and when. The judgment lives in
  the second half, and so does every way a fetch can go wrong, which is what
  makes `_BrowserFetcher` testable against a stand-in.
  """

  def start(self) -> None:
    """Launch the browser and wait until it answers; idempotent."""
    ...

  def request(self, path: str, *, decode: bool = True) -> object:
    """Call one of the browser's DevTools HTTP endpoints.

    `decode` is False for the endpoints answering prose rather than JSON,
    `/json/close/<id>` among them.
    """
    ...

  def open_tab(self, url: str) -> str:
    """Open `url` in a new tab, returning its target id."""
    ...

  def read_page(self, url: str) -> bytes:
    """Attach to the one open tab, read the page's own bytes, and detach."""
    ...

  def quit(self) -> None:
    """Shut the browser down and drop what it left behind; idempotent."""
    ...


class _DesktopBrowser:
  """A `_Browser` running in this account's own desktop session.

  Everything here follows from the one constraint the module docstring argues:
  nothing may be attached to a page while Cloudflare's challenge runs.

  - **The browser is launched, not driven.** `open` hands it to the account's
    own desktop session, and URLs arrive as tabs rather than as navigations, so
    no automation is in the picture when Cloudflare decides.
  - **Everything before the read speaks HTTP.** The DevTools HTTP endpoints
    attach no debugger to anything.
  - **The debugger attaches only to read, and detaches straight after**, so the
    next tab meets its own challenge unobserved. Disconnecting leaves the
    browser running, which is what lets one browser serve a whole run and lets
    the first page's clearance cookie spare the rest.

  One browser is launched per run, in a throwaway profile that goes with it.
  """

  def __init__(self) -> None:
    # One Playwright driver serves the whole run: it names the browser to
    # launch, and every later read connects through it. Only the connection is
    # made and dropped per read — the driver holding still attaches nothing to a
    # page, and starting one per read left asyncio complaining about its own
    # teardown on a run that had gone perfectly well.
    self._playwright: Playwright | None = None
    self._profile: Path | None = None
    self._port: int | None = None

  def start(self) -> None:
    """Launch the browser in a throwaway profile and wait for its port.

    `open` rather than the executable, because Claude's own session has no
    window server of its own: LaunchServices routes the launch into this
    account's desktop session, where the browser can render — which the
    challenge requires, headless being refused outright.

    Raises:
      RuntimeError: if the browser will not launch, or never answers.
    """
    if self._port:
      return

    port = _free_port()
    playwright = sync_playwright().start()
    self._playwright = playwright
    app = _browser_app(playwright)
    profile = Path(tempfile.mkdtemp(prefix='acbl-fetch-'))
    self._profile = profile
    try:
      subprocess.run(
        (
          'open',
          # `-a` names the application to launch, and `-n` demands a new
          # instance of it. Without `-n`, macOS would hand the request to an
          # instance already running and discard every flag below, leaving this
          # fetch pointed at someone else's profile and no debugging port.
          '-na',
          str(app),
          '--args',
          f'--user-data-dir={profile}',
          f'--remote-debugging-port={port}',
          # No window until a tab is asked for, so the only tab a run ever holds
          # is the one it opened — which is how `read_page` knows what to read.
          '--no-startup-window',
          '--no-first-run',
          '--no-default-browser-check',
        ),
        check=True,
      )
    except subprocess.CalledProcessError as error:
      raise RuntimeError(f'could not launch {app.name}: {error}') from error

    for _ in range(_BROWSER_START_TIMEOUT_SECONDS):
      try:
        _devtools_request(port, '/json/version')
      except OSError:
        time.sleep(_POLL_SECONDS)
      else:
        self._port = port
        logger.info(f'browser up on port {port}')
        return

    # Best effort: a browser still on its way up cannot be reached over CDP to
    # be told to quit, so one that binds the port just after this gives up is
    # orphaned anyway. Claiming the port is what lets `quit` try at all.
    self._port = port
    self.quit()
    raise RuntimeError(
      f'{app.name} did not answer port {port} within '
      f'{_BROWSER_START_TIMEOUT_SECONDS}s'
    )

  def request(self, path: str, *, decode: bool = True) -> object:
    """Call one of the browser's DevTools HTTP endpoints."""
    if not self._port:
      raise RuntimeError(f'the browser is not running, so cannot serve {path}')
    return _devtools_request(self._port, path, decode=decode)

  def open_tab(self, url: str) -> str:
    """Open `url` in a new tab, returning its target id.

    Raises:
      RuntimeError: if the browser answered with anything but a new target.
    """
    opened = self.request(f'/json/new?{urllib.parse.quote(url, safe="")}')
    if not isinstance(opened, dict) or 'id' not in opened:
      raise RuntimeError(f'browser would not open a tab for {url}: {opened!r}')
    return str(opened['id'])

  def read_page(self, url: str) -> bytes:
    """Attach, read the page's own bytes, and detach.

    The tab this fetch opened is the browser's only one, so the page is found by
    being the only one — Playwright exposes no target id to match on. Two things
    keep that true: `--no-startup-window`, so no tab exists that nobody asked
    for, and closing each attempt's tab as it ends. Any other count means one of
    these invariants has stopped holding, and picking whichever page came first
    would be a guess.
    """
    if not self._playwright:
      raise RuntimeError(f'the browser is not running, so cannot read {url}')

    browser = self._playwright.chromium.connect_over_cdp(
      f'http://127.0.0.1:{self._port}'
    )
    try:
      pages = [page for context in browser.contexts for page in context.pages]
      if len(pages) != 1:
        raise RuntimeError(
          f'expected the one tab opened for {url}, found {len(pages)}: '
          f'{[page.url for page in pages]}'
        )
      body: bytes = str(pages[0].evaluate(_PAGE_SOURCE_SCRIPT)).encode()
      return body
    finally:
      # Disconnects the debugger and leaves the browser running.
      browser.close()

  def quit(self) -> None:
    """Quit the browser and drop its profile; safe to call more than once."""
    if self._port and self._playwright:
      # A browser that has already gone is nothing to report at close time.
      with contextlib.suppress(OSError, PlaywrightError):
        browser = self._playwright.chromium.connect_over_cdp(
          f'http://127.0.0.1:{self._port}'
        )
        # Unlike `browser.close`, which only disconnects a browser reached over
        # CDP, this asks the browser itself to quit.
        browser.new_browser_cdp_session().send('Browser.close')
    self._port = None
    if self._playwright:
      self._playwright.stop()
      self._playwright = None
    if self._profile:
      shutil.rmtree(self._profile, ignore_errors=True)
      self._profile = None


class _BrowserFetcher:
  """A `fetch(url) -> bytes` that waits out Cloudflare.

  Holds the sequence a fetch follows, and the judgment about what to do when a
  step goes wrong; `_Browser` holds the browser itself.
  """

  def __init__(
    self,
    browser: _Browser | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
  ) -> None:
    """Fetch through `browser`, waiting between polls with `sleep`.

    Args:
      browser: the browser to drive; defaults to Chrome in this account's own
        desktop session.
      sleep: waits between clearance polls. A clock is a dependency like any
        other, and injecting it lets a test cover the waiting itself.
    """
    self._browser = browser or _DesktopBrowser()
    self._sleep = sleep
    self._started = False

  def __enter__(self) -> '_BrowserFetcher':
    return self

  def __exit__(self, *exception: object) -> None:
    self.close()

  def fetch(self, url: str) -> bytes:
    """Fetch a URL's own bytes, waiting out the challenge if one is served.

    A challenge that will not give way is worth trying again rather than
    abandoning: the difficulty varies between requests, and a run of them draws
    harder ones. Each attempt gets a fresh tab, and the browser — with whatever
    clearance it has already earned — is kept.

    Raises:
      RuntimeError: if the browser will not start, or no attempt got past the
        challenge.
    """
    if not self._started:
      self._browser.start()
      self._started = True

    failure: Exception | None = None
    for _ in range(_CHALLENGE_ATTEMPTS):
      target = self._browser.open_tab(url)
      try:
        self._wait_for_clearance(target, url)
        body = self._browser.read_page(url)
        # The read is its own request to the server, so it can be met by a
        # challenge of its own even though the page in front of it cleared one.
        # That interstitial names itself in its head; saving it as the capture
        # would be worse than trying again.
        if _CHALLENGE_TITLE.encode() in body[:_CHALLENGE_HEAD_BYTES]:
          raise RuntimeError(f'the read itself drew a challenge: {url}')
        return body
      except (RuntimeError, PlaywrightError) as error:
        # A `PlaywrightError` is usually the page giving way under the read —
        # the challenge re-navigating a tab mid-evaluate reads exactly like that
        # — and a fresh tab answers it as well as it answers a challenge that
        # never cleared.
        failure = error
        logger.warning(f'{error}; trying a fresh tab')
      finally:
        # A tab per attempt would accumulate across a run, and leaving only one
        # open is what lets the read find its page without a target id.
        try:
          self._browser.request(f'/json/close/{target}', decode=False)
        except OSError as close_error:
          # Raising here would replace the attempt's own failure — the one that
          # says why the fetch went wrong — with a closing error. A tab that
          # really did stay open is caught by the next attempt's one-tab check.
          logger.warning(f'could not close the tab for {url}: {close_error}')
    raise RuntimeError(
      f'could not fetch past Cloudflare in {_CHALLENGE_ATTEMPTS} attempts: '
      f'{url} (last: {failure})'
    ) from failure

  def _wait_for_clearance(self, target: str, url: str) -> None:
    """Poll a tab's title over HTTP until Cloudflare's interstitial gives way.

    An empty title means the tab has not painted yet, which is not clearance —
    only a title that is both present and not the interstitial's is.

    Raises:
      RuntimeError: if the interstitial is still there when the wait runs out.
    """
    seen: list[str] = []
    for _ in range(_CHALLENGE_TIMEOUT_SECONDS):
      listing = self._browser.request('/json/list')
      titles = [
        str(tab.get('title', ''))
        for tab in (listing if isinstance(listing, list) else [])
        if isinstance(tab, dict) and tab.get('id') == target
      ]
      if titles and titles[0] not in seen:
        seen.append(titles[0])
      if titles and titles[0] and _CHALLENGE_TITLE not in titles[0]:
        return
      self._sleep(_POLL_SECONDS)
    # Which titles the tab passed through separates a challenge that would not
    # give way from a tab that never loaded at all — the two need different
    # answers, and the timeout alone does not tell them apart.
    raise RuntimeError(
      f'Cloudflare did not clear within {_CHALLENGE_TIMEOUT_SECONDS}s: {url} '
      f'(titles seen: {seen})'
    )

  def close(self) -> None:
    """Shut the browser down; safe to call more than once."""
    self._browser.quit()
    self._started = False


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

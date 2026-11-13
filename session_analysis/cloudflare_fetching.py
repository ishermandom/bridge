# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Fetch pages that sit behind Cloudflare's challenge, through a real browser.

Cloudflare guards every ACBL page with a "managed challenge" — JavaScript a
browser must run before the real content is served — which a plain HTTP client
cannot satisfy. The challenge also refuses to clear at all while a debugger is
attached: it puts a getter-instrumented payload through every `console` method
and watches for the side effects of something serializing them. So a browser is
launched and left alone to meet the challenge, and the debugger attaches only
afterwards, to read the page. Headless is refused outright, whatever else is
true, so the browser is a visible one in this account's own desktop session.

`BrowserFetcher` is the entry point: a `fetch(url) -> bytes` that waits out the
challenge, which `acbl_fetching` uses to fetch its pages.
"""

import contextlib
import json
import logging
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from playwright.sync_api import (
  Error as PlaywrightError,
)
from playwright.sync_api import Playwright, sync_playwright

logger = logging.getLogger(__name__)


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


class _Browser(Protocol):
  """What a fetch needs a browser to do, apart from deciding when to do it.

  Drawing the line here keeps the half that cannot run without a real browser —
  launching one, calling its debugging endpoints, attaching to read a page —
  apart from the half that decides what to do and when. The judgment lives in
  the second half, and so does every way a fetch can go wrong, which is what
  makes `BrowserFetcher` testable against a stand-in.
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
          # Chrome encrypts its cookies with a key it keeps in the login
          # keychain, and asking for that key from a binary the keychain does
          # not trust raises a prompt in the desktop session, where nobody is
          # watching to answer it. The mock keychain uses a fixed in-memory key
          # instead, as Playwright's own launches do.
          '--use-mock-keychain',
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


class BrowserFetcher:
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

  def __enter__(self) -> BrowserFetcher:
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

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
true, so the browser is a visible one, on the virtual screen of a Linux virtual
machine (see `vm/README.md`).

`BrowserFetcher` is the entry point: a `fetch(url) -> bytes` that waits out the
challenge, which `acbl_fetching` uses to fetch its pages.
"""

import contextlib
import json
import logging
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Protocol

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
_BROWSER_EXIT_TIMEOUT_SECONDS = 30
_CHALLENGE_TIMEOUT_SECONDS = 60
_CHALLENGE_ATTEMPTS = 3
_POLL_SECONDS = 1
_DEVTOOLS_TIMEOUT_SECONDS = 20

# The directory describing the browser's Linux virtual machine; its `start.sh`
# readies the VM.
_VIRTUAL_MACHINE_DIRECTORY = Path(__file__).resolve().parents[1] / 'vm'
# Where `vm/setup.sh` installs Chrome in the VM.
_VIRTUAL_MACHINE_CHROME = '/opt/chrome-linux-arm64/chrome'
# The ports Chrome's debugging endpoint may use, each of which the VM forwards
# to the same number on the Mac. `vm/lima.yaml` names the same range, so the two
# change together.
_DEBUGGING_PORTS = range(29220, 29230)

# A shell script that runs Chrome in the VM until the script's input closes,
# then ends Chrome and drops its throwaway profile. The input closes when the
# fetch ends, even if it crashes, so Chrome ends with its fetch unless it
# ignores the signal to exit. `$0` is Chrome's path and `$@` its flags; display
# `:2` is the one `vm/setup.sh` reserves for session analysis fetches.
_BROWSER_SESSION_SCRIPT = """
profile=$(mktemp -d)
DISPLAY=:2 "$0" --user-data-dir="$profile" "$@" &
chrome=$!
cat > /dev/null
kill "$chrome" 2> /dev/null
wait "$chrome"
rm -rf "$profile"
"""


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
  """An unused debugging port from `_DEBUGGING_PORTS`.

  Checking the Mac alone suffices: the VM forwards each port Chrome listens on,
  so a port another fetch's browser holds is taken on the Mac too. A fixed port
  would instead let a second fetch reach the first one's browser.

  Raises:
    RuntimeError: if every port in `_DEBUGGING_PORTS` is taken.
  """
  for port in _DEBUGGING_PORTS:
    with socket.socket() as probe:
      try:
        probe.bind(('127.0.0.1', port))
      except OSError:
        continue
      return port
  raise RuntimeError(
    f'every debugging port from {_DEBUGGING_PORTS.start} to '
    f'{_DEBUGGING_PORTS.stop - 1} is taken on the Mac'
  )


def _start_virtual_machine() -> str:
  """Ready the Linux virtual machine, returning its name for `limactl`.

  Raises:
    RuntimeError: if the VM will not start.
  """
  try:
    started = subprocess.run(
      ('bash', str(_VIRTUAL_MACHINE_DIRECTORY / 'start.sh')),
      check=True,
      stdout=subprocess.PIPE,
      text=True,
    )
  except subprocess.CalledProcessError as error:
    raise RuntimeError(f'could not ready the Linux VM: {error}') from error
  return started.stdout.strip()


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


class _VirtualMachineBrowser:
  """A `_Browser` running in a Linux virtual machine.

  The VM gives Chrome a virtual screen to draw on, so a fetch needs no desktop
  session on the Mac. Everything else follows from the one constraint the module
  docstring argues: nothing may be attached to a page while Cloudflare's
  challenge runs.

  - **The browser is launched, not driven.** A shell in the VM starts it, and
    URLs arrive as tabs rather than as navigations, so no automation is in the
    picture when Cloudflare decides.
  - **Everything before the read speaks HTTP.** The DevTools HTTP endpoints
    attach no debugger to anything.
  - **The debugger attaches only to read, and detaches straight after**, so the
    next tab meets its own challenge unobserved. Disconnecting leaves the
    browser running, which is what lets one browser serve a whole run and lets
    the first page's clearance cookie spare the rest.

  One browser is launched per run, in a throwaway profile that goes with it. The
  `limactl shell` that launches it stays open for the whole run, and the VM
  counts an open shell as work, so the VM can't power itself off mid-fetch.
  """

  def __init__(self) -> None:
    # One Playwright driver serves the whole run, and every read connects
    # through it. Only the connection is made and dropped per read — the driver
    # holding still attaches nothing to a page, and starting one per read left
    # asyncio complaining about its own teardown on a run that had gone
    # perfectly well.
    self._playwright: Playwright | None = None
    self._port: int | None = None
    # Releases what a successful `start` acquired, in the reverse order.
    self._resources = contextlib.ExitStack()

  def start(self) -> None:
    """Ready the VM, launch the browser in it, and wait for its port.

    Raises:
      RuntimeError: if the VM or the browser will not start, or the
        browser never answers.
    """
    if self._port:
      return

    instance = _start_virtual_machine()
    port = _free_port()
    command = (
      *('limactl', 'shell', '--workdir', '/', instance, '--'),
      *('sh', '-c', _BROWSER_SESSION_SCRIPT, _VIRTUAL_MACHINE_CHROME),
      f'--remote-debugging-port={port}',
      # No window until a tab is asked for, so the only tab a run ever holds is
      # the one it opened — which is how `read_page` knows what to read.
      '--no-startup-window',
      '--no-first-run',
      '--no-default-browser-check',
      # The VM runs no keyring for Chrome to keep its cookie key in, so the key
      # stays in the throwaway profile instead.
      '--password-store=basic',
    )
    # Everything acquired here is released on leaving this block, unless the
    # browser answers, in which case `pop_all` hands it all to `quit`.
    with contextlib.ExitStack() as resources:
      # What the browser's session prints, for an error message.
      output = resources.enter_context(tempfile.TemporaryFile())
      try:
        session = subprocess.Popen(
          command,
          # The script runs until this input closes, which `quit` does.
          stdin=subprocess.PIPE,
          stdout=output,
          stderr=subprocess.STDOUT,
        )
      except OSError as error:
        raise RuntimeError(f'could not run {command[0]}: {error}') from error
      resources.callback(_end_session, session, output)
      playwright = resources.enter_context(sync_playwright())

      for _ in range(_BROWSER_START_TIMEOUT_SECONDS):
        if session.poll() is not None:
          break
        try:
          _devtools_request(port, '/json/version')
        except OSError:
          time.sleep(_POLL_SECONDS)
        else:
          self._playwright = playwright
          self._port = port
          self._resources = resources.pop_all()
          logger.info(f'browser up on port {port} in VM {instance}')
          return

      raise RuntimeError(
        f'the browser in VM {instance} did not answer port {port} '
        f'within {_BROWSER_START_TIMEOUT_SECONDS}s (session exit status: '
        f'{session.poll()}); its output ends: {_excerpt(output)!r}'
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
    self._port = None
    self._playwright = None
    self._resources.close()


def _end_session(session: subprocess.Popen[bytes], output: IO[bytes]) -> None:
  """End a session `_VirtualMachineBrowser` started, and wait for it to exit.

  Closing the session's input ends the browser, and the session then drops the
  browser's profile and exits.
  """
  if session.stdin:
    session.stdin.close()
  try:
    session.wait(timeout=_BROWSER_EXIT_TIMEOUT_SECONDS)
  except subprocess.TimeoutExpired:
    # The browser ignored being told to exit and may live on in the VM, keeping
    # it awake. Killing `limactl` below only ends the wait: `limactl` starts
    # `ssh` as a separate process, which survives the kill and keeps the session
    # open.
    #
    # TODO: have `_BROWSER_SESSION_SCRIPT` kill the browser outright when it
    # ignores being told to exit, should that ever happen.
    logger.warning(
      f'the browser did not exit within {_BROWSER_EXIT_TIMEOUT_SECONDS}s of '
      f'being told to, and may still be running in the VM, keeping it '
      f'awake; its output ends: {_excerpt(output)!r}'
    )
    session.kill()


def _excerpt(output: IO[bytes]) -> str:
  """The end of what a browser session has printed, for an error message."""
  output.seek(0)
  return output.read().decode(errors='replace')[-2000:]


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
      browser: the browser to drive; defaults to Chrome in a Linux virtual
        machine.
      sleep: waits between clearance polls. A clock is a dependency like any
        other, and injecting it lets a test cover the waiting itself.
    """
    self._browser = browser or _VirtualMachineBrowser()
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

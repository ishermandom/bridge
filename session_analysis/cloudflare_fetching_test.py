# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for waiting out Cloudflare's challenge through a browser.

`BrowserFetcher` is exercised against `_FakeBrowser`, which scripts the tab
titles and page reads a real browser would give, so tests need neither a browser
nor the network.
"""

from collections.abc import Sequence

import pytest
from playwright.sync_api import Error as PlaywrightError

from session_analysis.cloudflare_fetching import BrowserFetcher

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
  return BrowserFetcher(browser, sleep=lambda _: None).fetch(url)


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
  fetcher = BrowserFetcher(browser, sleep=lambda _: None)

  fetcher.fetch('https://live.acbl.org/one')
  fetcher.fetch('https://live.acbl.org/two')

  # Two tabs, one browser: the second fetch reuses whatever clearance the first
  # earned.
  assert len(browser.opened) == 2
  assert browser.started


def test_leaving_the_context_quits_the_browser() -> None:
  browser = _FakeBrowser()

  with BrowserFetcher(browser, sleep=lambda _: None) as fetcher:
    fetcher.fetch('https://live.acbl.org/x')

  assert browser.quit_called

#!/usr/bin/env python3
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Check the reservations userscript against the live bridge club site.

The userscript adjusts a page this project does not control, so its selectors
hold only until the site changes its markup. The unit and jsdom tests prove the
logic is internally consistent against synthetic markup; only a run against the
real page proves the markup still matches. This script is that third tier — it
injects the userscript into a real browser, drives each convenience, and reports
which ones still fire. See spec.md `#testing-strategy`.

**It never books anything.** The script opens modals and reads their state,
never clicking a save or submit control. As a backstop, an HTTP request guard
lets through only the known subset of safe requests. Even an unintended click
therefore cannot book a game.

The live run itself stays out of `run_tests.sh`: it needs the network and the
live site, so it runs by hand when the site looks like it has changed. Only the
guard's rule is unit tested, through `verify_live_test.py`.

```shell
.venv/bin/python club_sites/palo_alto/verify_live.py --name 'Some Player'
```

`--name` must be a name the site's player directory knows, since one check
confirms the autocomplete binds a real player record behind the typed text.
Nothing is stored, and neither the name nor any page markup is written to disk —
the live page carries other members' names throughout.
"""

import argparse
import dataclasses
import json
import pathlib
import sys
import urllib.parse
from collections.abc import Sequence

from playwright.sync_api import (
  Browser,
  Page,
  Request,
  Route,
  WebSocketRoute,
  sync_playwright,
)
from playwright.sync_api import (
  TimeoutError as PlaywrightTimeoutError,
)

RESERVATIONS_URL = 'https://paloaltobridge.org/reservations/'

USERSCRIPT_PATH = pathlib.Path(__file__).parent / 'pabc-reservations.user.js'

# The site keeps rendering well past `load`; these cover its own passes and the
# userscript's `MutationObserver` reacting to them.
PAGE_SETTLE_MS = 2500
SCRIPT_SETTLE_MS = 1500
# A modal's prefills wait on the site's autocomplete round trip.
MODAL_SETTLE_MS = 3000
# How long one game gets to open its reserve modal, and how many games are tried
# before giving up. A game the site will not take a reservation for — one that
# has already started, most often — answers with an alert instead, so a check
# has to be free to move on to the next game rather than conclude the feature is
# broken.
MODAL_OPEN_TIMEOUT_MS = 8000
RESERVE_CANDIDATE_ROWS = 10

# The stored direction every check expects, matching the profile stubbed below.
EXPECTED_DIRECTION = 'E-W'

# The site funnels its data calls — reads and writes alike — through POSTs to
# one endpoint, `action.php`, distinguished by an `action` field in the JSON
# body. The HTTP method therefore cannot tell a lookup from a booking, so the
# guard allowlists the two read actions these checks need and refuses every
# other action.
READ_ACTIONS = frozenset({'keyword', 'recentPartners'})

# Playwright's names for the resource types a page fetches to build itself.
# Fetched by GET, these pass from any host: the page cannot render without them,
# and the site sends its data calls as fetches rather than as resource loads.
PAGE_BUILDING_RESOURCES = frozenset(
  {'script', 'stylesheet', 'image', 'font', 'media'}
)


@dataclasses.dataclass(frozen=True)
class CheckResult:
  """One verified convenience, and what the page actually showed."""

  name: str
  passed: bool
  detail: str


# Wide enough for every check name above, so the details line up in a column
# even though each line prints before the next check has run.
NAME_COLUMN_WIDTH = 24


def _reported(result: CheckResult) -> CheckResult:
  """Print a finished check, and hand it back to be collected."""
  mark = 'PASS' if result.passed else 'FAIL'
  print(
    f'{mark}  {result.name:<{NAME_COLUMN_WIDTH}}  {result.detail}', flush=True
  )
  return result


@dataclasses.dataclass(frozen=True)
class ReserveModalState:
  """The reserve modal's fields, as the userscript left them."""

  banner: str | None
  player_text: str
  # The site binds the chosen player record to the field as `data-id`. Matching
  # text alone would not prove the record was bound, which is the whole point of
  # driving the autocomplete rather than typing free text.
  bound_player_id: str | None
  direction: str | None
  section: str | None

  def summary(self) -> str:
    """A one-line rendering for the report."""
    return (
      f'player={self.player_text!r} id={self.bound_player_id} '
      f'direction={self.direction} section={self.section!r} '
      f'banner={"yes" if self.banner else "no"}'
    )


@dataclasses.dataclass(frozen=True)
class RequestSummary:
  """A request reduced to the fields that decide whether the guard allows it."""

  method: str
  # Playwright's name for what the request fetches: `document`, `script`,
  # `fetch`, `xhr`, `ping`, and so on.
  resource_type: str
  url: str
  # The `action` a data call's JSON body names; None when it names none.
  action: str | None


def requested_action(body: bytes | None) -> str | None:
  """The `action` a request body names, or None when it names none.

  Takes raw bytes rather than Playwright's decoded `post_data`, which raises on
  a body that isn't UTF-8 — and a guard that raises leaves its request neither
  allowed nor refused.
  """
  if not body:
    return None

  try:
    parsed: object = json.loads(body)
  except (json.JSONDecodeError, UnicodeDecodeError):
    return None

  if not isinstance(parsed, dict):
    return None
  action = parsed.get('action')
  return action if isinstance(action, str) else None


def is_allowed(request: RequestSummary) -> bool:
  """Whether the guard lets a request reach the network.

  Allows only these requests:

  - the reservations page itself;
  - the resources that build it (`PAGE_BUILDING_RESOURCES`), fetched by GET;
  - a POST to the site's `action.php` naming one of `READ_ACTIONS`.
  """
  if request.method == 'GET':
    if request.resource_type == 'document':
      return request.url == RESERVATIONS_URL
    return request.resource_type in PAGE_BUILDING_RESOURCES

  url = urllib.parse.urlsplit(request.url)
  return (
    request.method == 'POST'
    and url.hostname == 'paloaltobridge.org'
    and url.path.endswith('/action.php')
    and request.action in READ_ACTIONS
  )


def _guard_request(route: Route, request: Request) -> None:
  """Let allowed requests through and refuse the rest.

  The safety net behind "never book a reservation"; `is_allowed` holds the rule.
  A refusal is announced rather than swallowed: blocking a read the site newly
  depends on would otherwise surface only as a mystifying check failure further
  down.
  """
  summary = RequestSummary(
    method=request.method,
    resource_type=request.resource_type,
    url=request.url,
    action=requested_action(request.post_data_buffer),
  )
  if is_allowed(summary):
    route.continue_()
    return

  print(
    f'blocked {summary.method} {summary.resource_type} {summary.url} '
    f'(action={summary.action!r})',
    flush=True,
  )
  route.abort()


def _refuse_web_socket(web_socket: WebSocketRoute) -> None:
  """Keep a WebSocket from ever reaching the server.

  Playwright connects a socket routed here only if the handler calls
  `connect_to_server`, so not calling it is the refusal: the page sees a socket
  that opens but reaches no one. Closing the socket instead isn't an option,
  since `WebSocketRoute.close` hangs when called from a handler under the sync
  API.
  """
  print(f'blocked WebSocket {web_socket.url}', flush=True)


def open_read_only_page(browser: Browser) -> Page:
  """Open a page that can read from the site but never write to it.

  Every request the page makes goes through the guard, which sits on the browser
  context rather than the page, so a popup or new tab the site opens is held to
  it too. Two channels bypass request routing and are shut separately: service
  workers are blocked outright, and WebSockets go to `_refuse_web_socket`.
  """
  context = browser.new_context(
    viewport={'width': 1400, 'height': 1000}, service_workers='block'
  )
  context.route('**/*', _guard_request)
  context.route_web_socket('**/*', _refuse_web_socket)
  return context.new_page()


def _gm_storage_stub(name: str, email: str) -> str:
  """A stand-in for Tampermonkey's storage, holding one profile.

  The userscript runs its page wiring only where `GM_getValue` exists, so this
  both supplies the profile and switches the script on.
  """
  return f"""
    window.__pabcProfile = {{
      profile: {{
        name: {name!r},
        email: {email!r},
        direction: {EXPECTED_DIRECTION!r},
      }},
    }};
    window.GM_getValue = (key, fallback) =>
      window.__pabcProfile[key] ?? fallback;
    window.GM_setValue = () => {{}};
  """


def _open_reserve_modal(page: Page, row_selector: str) -> str:
  """Open the reserve modal from a game row, and name the game it opened for.

  Tries matching rows in turn, because not every game can be reserved: one that
  has already started answers with an alert instead of the modal, and the games
  list rolls forward daily, so which rows are in the past changes by the hour.
  Rather than reimplement the site's rules about what is still reservable, this
  clicks and reads what came back. Trying rows in turn also absorbs the table
  being rebuilt underfoot, which detaches a row a locator just resolved.

  Clicks through the mouse, deliberately: `new-reserve-button` defines its own
  `click()` that opens the modal without dispatching a click event, so a
  scripted `element.click()` would silently skip every click listener —
  including the one that arms the limited-game banner.
  """
  rows = page.locator(row_selector)
  for index in range(min(rows.count(), RESERVE_CANDIDATE_ROWS)):
    button = rows.nth(index).locator('new-reserve-button').first
    name = rows.nth(index).get_attribute('data-name') or '(unnamed game)'
    button.scroll_into_view_if_needed()
    button.click()

    try:
      # Confirm the modal is showing rather than sleeping a fixed interval and
      # hoping. Without this the fields read back could be the previous game's,
      # which passes or fails on its own merits and measures nothing.
      page.wait_for_function(
        "() => document.querySelector('#newReservation')"
        ".matches(':popover-open')",
        timeout=MODAL_OPEN_TIMEOUT_MS,
      )
    except PlaywrightTimeoutError:
      refusal = page.evaluate("""() =>
        document.querySelector('custom-modal.alert dialog[open] .message')
          ?.textContent?.trim() ?? ''""")
      print(
        f'{name}: {refusal or "no reserve modal"} — trying the next game',
        flush=True,
      )
      # The alert is modal: left up, it swallows every later click.
      _close_modal(page)
      continue

    # The prefills still wait on the site's autocomplete round trip.
    page.wait_for_timeout(MODAL_SETTLE_MS)
    return name

  raise RuntimeError(
    f'none of the first {RESERVE_CANDIDATE_ROWS} rows matching {row_selector!r} '
    'would open a reserve modal'
  )


def _read_reserve_modal(page: Page) -> ReserveModalState:
  """Read the reserve modal's prefilled fields."""
  state = page.evaluate("""() => {
    const modal = document.querySelector('#newReservation');
    const player = modal.querySelector('input[name="player"]');
    return {
      banner: modal.querySelector('.pabc-reserve-banner')?.textContent ?? null,
      playerText: player.value,
      boundPlayerId: player.dataset.id || null,
      direction: modal.querySelector('#direction')?.value ?? null,
      section: modal.querySelector('#sectionMenu')?.value ?? null,
    };
  }""")
  return ReserveModalState(
    banner=state['banner'],
    player_text=state['playerText'],
    bound_player_id=state['boundPlayerId'],
    direction=state['direction'],
    section=state['section'],
  )


def _close_modal(page: Page) -> None:
  """Close every open modal, without touching any of their buttons.

  Closes them through the platform's own methods rather than pressing Escape,
  which only reaches a modal that holds focus, and confirms they are shut before
  returning — the next check's click has to land on a button rather than on a
  modal still covering it.
  """
  page.evaluate("""() => {
    for (const popover of document.querySelectorAll('[popover]')) {
      if (popover.matches(':popover-open')) {
        popover.hidePopover();
      }
    }
    for (const dialog of document.querySelectorAll('dialog[open]')) {
      dialog.close();
    }
  }""")
  page.wait_for_function(
    "() => !document.querySelector('[popover]:popover-open')"
    " && !document.querySelector('dialog[open]')"
  )


def _reserve_prefills_landed(modal: ReserveModalState, name: str) -> bool:
  """Whether the identity prefills bound correctly, banner aside."""
  return bool(
    modal.bound_player_id
    and modal.player_text.lower() == name.lower()
    and modal.direction == EXPECTED_DIRECTION
  )


def check_settings_panel(page: Page) -> CheckResult:
  """The settings gear is mounted on the page."""
  count = page.locator('#pabcHelperGear').count()
  return CheckResult('settings gear', count == 1, f'{count} found')


def check_game_list_expanded(page: Page) -> CheckResult:
  """The "Show more games" section was expanded on load."""
  label: str = page.evaluate(
    "() => document.querySelector('#showMore')?.textContent ?? ''"
  )
  # The same control reads "Show less" once the list is open.
  return CheckResult(
    'game list expanded', 'less' in label.lower(), f'toggle reads {label!r}'
  )


def check_limited_games_flagged(page: Page) -> CheckResult:
  """Every game carrying a masterpoint ceiling is flagged limited.

  Tests the ceiling signal alone rather than re-deriving `isLimitedGame` here: a
  second copy of that rule would drift from the userscript's. A ceiling by
  itself is enough to make a game limited, so an unflagged one is a real failure
  — while a game flagged on its title instead is correctly ignored here.
  """
  unflagged: list[str] = page.evaluate("""() =>
    [...document.querySelectorAll('tr[data-name][data-mps]')]
      .filter((row) => row.dataset.mps !== ''
                       && !row.classList.contains('pabc-limited'))
      .map((row) => row.dataset.name)""")
  flagged = page.locator('tr.pabc-limited').count()
  badges = page.locator('.pabc-limited-badge').count()

  detail = f'{flagged} rows flagged, {badges} badged'
  if unflagged:
    detail = f'{detail}; missed {sorted(set(unflagged))}'
  return CheckResult('limited games flagged', not unflagged, detail)


def check_limited_reserve(page: Page, name: str) -> CheckResult:
  """A limited game's reserve modal warns, and still prefills the player."""
  game = _open_reserve_modal(page, 'tr.pabc-limited')
  modal = _read_reserve_modal(page)
  _close_modal(page)

  passed = bool(modal.banner) and _reserve_prefills_landed(modal, name)
  return CheckResult(
    'limited game warns', passed, f'{game!r} — {modal.summary()}'
  )


def check_open_reserve(page: Page, name: str) -> CheckResult:
  """An open game reserves cleanly, showing no leftover warning.

  Runs straight after the limited-game check on purpose: the banner rides a
  carry-over flag consumed at the next open, so this is where a flag left armed
  would surface as a spurious warning.
  """
  game = _open_reserve_modal(page, 'tr[data-name]:not(.pabc-limited)')
  modal = _read_reserve_modal(page)
  _close_modal(page)

  passed = modal.banner is None and _reserve_prefills_landed(modal, name)
  return CheckResult(
    'open game reserves', passed, f'{game!r} — {modal.summary()}'
  )


def check_my_reservations(page: Page, name: str) -> CheckResult:
  """The lookup modal offers the stored name, without submitting it.

  The name must be typed *and* the site's dropdown opened, since the entry is
  what the user clicks. Selecting it here would submit the lookup and close the
  modal, so the check confirms the entry is offered and left alone.
  """
  page.evaluate(
    "() => document.querySelector('#myReservationsDialog').showPopover()"
  )
  page.wait_for_timeout(MODAL_SETTLE_MS)

  field: str = page.evaluate("""() =>
    document.querySelector('#myReservationsDialog input.needsDropdown')
      ?.value ?? ''""")
  entries: list[str] = page.evaluate("""() =>
    [...document.querySelectorAll('#myReservationsDialog ul.dropdown li')]
      .map((item) => item.textContent)""")
  _close_modal(page)

  offered = name.lower() in [entry.lower() for entry in entries]
  passed = field.lower() == name.lower() and offered
  return CheckResult(
    'lookup name offered',
    passed,
    f'field={field!r}, {len(entries)} dropdown entries',
  )


def check_cancel_email(page: Page, email: str) -> CheckResult:
  """The cancellation modal's confirmation email is prefilled."""
  page.evaluate(
    "() => document.querySelector('cancel-reservation-modal dialog')"
    '.showModal()'
  )
  page.wait_for_timeout(1500)

  filled: str = page.evaluate("""() =>
    document.querySelector('cancel-reservation-modal dialog .inputDiv input')
      ?.value ?? ''""")
  _close_modal(page)
  return CheckResult('cancel email prefilled', filled == email, f'{filled!r}')


def run_checks(page: Page, name: str, email: str) -> Sequence[CheckResult]:
  """Drive every convenience in turn, reporting each as it finishes.

  Ordered, not independent: the open-game reserve check relies on running
  directly after the limited-game one.

  Each result prints as it lands rather than at the end. A check drives a live
  page over several seconds and can hang on one the site has changed, and a
  report withheld until the finish would take everything already learned down
  with it.
  """
  return [
    _reported(check_settings_panel(page)),
    _reported(check_game_list_expanded(page)),
    _reported(check_limited_games_flagged(page)),
    _reported(check_limited_reserve(page, name)),
    _reported(check_open_reserve(page, name)),
    _reported(check_my_reservations(page, name)),
    _reported(check_cancel_email(page, email)),
  ]


def verify(name: str, email: str, headless: bool) -> Sequence[CheckResult]:
  """Load the live page with the userscript injected, then run every check."""
  with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=headless)
    page = open_read_only_page(browser)
    page.add_init_script(_gm_storage_stub(name, email))

    page.goto(RESERVATIONS_URL, wait_until='networkidle', timeout=60_000)
    page.wait_for_timeout(PAGE_SETTLE_MS)
    # The site shows a one-time help video, gated by a cookie a fresh browser
    # profile does not carry. Left open, it swallows every click.
    page.evaluate("() => document.querySelector('#videoHelp')?.close()")

    # Injected once the page has settled, the way Tampermonkey runs it at
    # `document-idle`.
    page.evaluate(USERSCRIPT_PATH.read_text())
    page.wait_for_timeout(SCRIPT_SETTLE_MS)

    results = run_checks(page, name, email)
    browser.close()
    return results


def report(results: Sequence[CheckResult]) -> bool:
  """Summarize the run and return whether every check passed.

  The per-check lines are already out, printed by `run_checks` as each landed.
  """
  failures = [result for result in results if not result.passed]
  print()
  if failures:
    print(
      f'{len(failures)} of {len(results)} checks failed — the site has '
      'likely moved its markup. spec.md records what each feature depends on.'
    )
  else:
    print(f'All {len(results)} checks passed.')
  return not failures


def main(argv: Sequence[str] | None = None) -> int:
  """Parse arguments, run the verification, and report."""
  parser = argparse.ArgumentParser(
    description='Check the reservations userscript against the live site.'
  )
  parser.add_argument(
    '--name',
    required=True,
    help='a full name the live player directory knows; one check confirms '
    'the autocomplete binds its player record',
  )
  parser.add_argument(
    '--email',
    default='player@example.com',
    help='any address — only checked for landing in the cancel field, and '
    'never submitted',
  )
  parser.add_argument(
    '--headed',
    action='store_true',
    help='show the browser, to watch the flows run',
  )
  args = parser.parse_args(argv)

  return 0 if report(verify(args.name, args.email, not args.headed)) else 1


if __name__ == '__main__':
  sys.exit(main())

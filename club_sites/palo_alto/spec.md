# Palo Alto Bridge Center reservations helper

A userscript that adds personal conveniences to the reservations page at
`https://paloaltobridge.org/reservations/`: it prefills the user's identity,
expands the game list, defaults the section to "Open", and guards against
accidentally booking a limited game.

The project README (`club_sites/palo_alto/README.md`) describes the features and
setup for someone using the helper; this document is the design record for
someone building or changing it, and references that README rather than
restating it. For where the project sits among the others in the repository, see
the top-level `README.md`.

## Goals and scope

The page is a JavaScript-rendered single-page app. Every convenience here is a
client-side adjustment applied to that page as the user browses it normally in
their own browser — not a separate automation that drives the site.

In scope: the conveniences listed in the project README — the identity prefills,
the East/West direction default, the "Open" section default, the expanded game
list, and the visual limited-game flag — plus an in-page settings panel for
editing the stored profile. The README is the user-facing source for what each
does; the sections below record how they work and why.

Out of scope / deferred:

- Prefilling partner name or optional contact fields (ACBL number, phone). The
  profile is intentionally just name, email, and direction.
- A hard block on booking limited games. The guard is visual only to prevent
  accidental bookings without interfering with intentional ones.

## Platform and packaging

**A single userscript, run by Tampermonkey, targeting Chrome.** Rationale:

- Every requirement is "when this page loads, adjust the DOM and fill fields
  from stored values." That is the userscript sweet spot. A browser extension
  would add manifest, build, and distribution overhead for capabilities
  (background logic, a dedicated options page, cross-site reach) this project
  doesn't need.
- On Chrome, Violentmonkey is effectively unavailable (still Manifest V2, no V3
  rewrite planned), so Tampermonkey is the practical manager. The script is
  written to the standard `GM_*` API, so it also runs unchanged under ScriptCat,
  or under Tampermonkey on other browsers — cross-browser support is incidental
  and free, not a target.

**Permissions are locked down.** The setup — restricting Tampermonkey's site
access to `paloaltobridge.org` — is covered in the project README. The design
consequence recorded here: that restriction costs only the manager features that
reach other domains (automatic script-update checks, cross-origin
`GM_xmlhttpRequest`, `file://` resources), none of which this script uses. So
the script depends on **no host-permission APIs** — profile storage uses
`GM_setValue`/`GM_getValue` (granted capabilities, not host access), and updates
are applied by pasting a new version into Tampermonkey rather than auto-update.

The userscript's `@version` is the canonical version — the one value to bump per
release, and the one Tampermonkey reads. With no build step there is nothing to
share it with `package.json`, whose version is irrelevant to a private,
unpublished test harness and is pinned to a static `0.0.0` placeholder so it
never needs touching.

## Repository placement

The helper lives in `club_sites/palo_alto/`. The `club_sites/` parent groups
per-club website tooling, one subdirectory per club, so a second club's tooling
sits in its own sibling (`club_sites/<club>/`) rather than a generic shared
directory.

The directory holds:

- `club_sites/palo_alto/pabc-reservations.user.js` — the userscript, carrying
  the standard MIT license block.
- `club_sites/palo_alto/README.md` — install and lock-down steps for the user
  (install Tampermonkey, enable "Allow user scripts", set site-scoped access,
  paste the script).
- `club_sites/palo_alto/verify_live.py` — the live-site check described under
  `#testing-strategy`. Uses Playwright to drive a real browser.
- `club_sites/palo_alto/pyproject.toml` — the Python half of the tooling,
  declaring Playwright. It carries the same project name as `package.json`
  beside it: one project spanning two toolchains, each manifest declaring what
  its own half needs.

## Profile model and storage

The profile is three fields:

- `name` — the user's full name as the site expects it.
- `email` — used when canceling.
- `direction` — `EW` or `NS`; defaults to and is normally `EW`.

Stored via `GM_setValue`/`GM_getValue` so it survives script edits. Edited
through an **in-page settings panel**: a small UI injected onto the reservations
page (e.g. a gear control that opens a panel with the three fields and a Save
button). The panel is the only writer of the stored profile; every feature below
reads from storage.

## Security model

The profile is low-sensitivity — a name, an email, and a direction string, no
credentials or payment data — but the storage and manager choices were made
deliberately, and the reasoning is worth recording so it isn't re-litigated.

**Feeding the data to the site is the point.** The script's whole job is to put
name, email, and direction into the reservation forms, so the site receiving
that data is intended behavior, not a leak. The storage choice is therefore not
about hiding data from the site — it is about reliability and isolation from the
site's own state.

**Why GM storage.** `GM_setValue` data is held in Tampermonkey's own per-script
storage inside the browser profile, separate from the site's origin storage. It
was chosen over cookies and `localStorage` on practical grounds: it is the
persistence API built for userscripts, namespaced per script so it cannot
collide with the site's own keys, and it survives clearing the site's data —
whereas cookies and `localStorage` live in the site's own storage, can be read
or overwritten by the site's code, and are wiped when site data is cleared.

**The threat that does matter is the manager, not the site.** GM storage offers
no protection against a compromised userscript _manager_ exfiltrating to third
parties or snooping other sites. A manager injects code into every page it is
allowed on, so on `paloaltobridge.org` it can read the form and capture the name
and email as they are typed — independent of where they are stored. The storage
choice is neutral to this threat.

**What actually bounds the risk.** Two things, neither of them the storage
choice:

- **Site-scoping.** Tampermonkey's host access is restricted to
  `paloaltobridge.org` (see "Platform and packaging"), so a compromised manager
  can see only that one site. This is the primary mitigation.
- **Low data sensitivity.** Even full compromise of the profile exposes only a
  name and email, which bounds the worst case.

**Manager choice.** Trusting any userscript manager means trusting it with code
injection on the allowed site, so the manager itself is the real trust decision
— not the storage API. Tampermonkey (closed-source) is accepted here on the
strength of its maturity and large user base; an open-source manager is not
treated as inherently more trustworthy absent a comparably large, active
community to audit it. Because the script uses only the standard `GM_*` API, the
manager can be swapped later without code changes if that assessment shifts.

Rejected alternatives, as of June 18, 2026:

- [Violentmonkey](https://violentmonkey.github.io/) is not currently supported
  on Chrome, due its out of date Manifest V2 architecture.
- ScriptCat is an open source alternative, but currently has a smaller community
  base.

## Features

Each feature activates only on the relevant part of the page and degrades
quietly if the page markup it targets is absent — a missing element means the
site changed, which should be visible in manual testing, not silently break
unrelated features. Prefills fill only an empty field or a control still at its
default — they never overwrite something the user has already typed or chosen.

- **Prefill name when reserving.** Fill the reservation flow's name field from
  the stored name. See "Hard parts" — the name field is an autocomplete that
  likely binds a player record, so this is the riskiest feature.
- **Prefill name when looking up reservations.** Type the stored name into the
  "My Reservations" name field, but do not select a dropdown entry — on that
  modal selecting submits and closes it, and the user may want to look up a
  different player. (Reserving differs: there, selecting advances the form, so
  that prefill does select.)
- **Prefill email when canceling.** Fill the email field in the cancellation
  flow from the stored email.
- **Prefill direction.** Set the N/S-vs-E/W direction preference in the reserve
  flow to the stored direction (normally E/W). Editable afterward.
- **Default section to "Open".** When a reservation offers a section dropdown,
  pre-select "Open". Left editable, consistent with the other prefills, so the
  user can still choose another section and the feature is harmless when a game
  has no "Open" section.
- **Expand "Show more games".** Programmatically expand the collapsed section on
  page load so all games are visible by default.
- **Hide the Firecracker fireworks.** The site spawns `<firework-element>`
  animations during the Firecracker sectional; a CSS rule hides them. Purely
  cosmetic, and the only feature implemented as a static style rather than
  behavior.

## Limited-game guard

Goal: make it unlikely the user books a game they're not trying to book (the
canonical case is EZ Bridge, a beginner game). The guard is **visual only** — it
makes limited games conspicuous but does not intercept or block booking. This
light approach was chosen deliberately, to minimize friction in case the user
does wish to book a limited game on occasion.

**Detection** uses two independent signals, either sufficient to mark a game
limited:

- the **masterpoint ceiling** on the row's `data-mps` (e.g. EZ Bridge at 49);
  and
- a **restriction named in the game's title/subtitle** (`data-name` +
  `data-special`) — a beginner/NLM/Mid-Flight label, or a masterpoint cap like
  `0-3000MP` or `0-99`.

The ceiling alone is unreliable: the site populates `data-mps` inconsistently,
carrying it on some instances of an event and omitting it on others, so the
title-based check is needed as a backstop. The title is checked rather than the
section list, because sections are overloaded — an open stratified game lists a
`<500MP` section yet is open to all through its `Open` section, and
session/bracket logistics (`Morning only`, `Bracketed teams`) share the same
field, so a section-based rule both over- and under-flags.

Detection is a **pure function** of the ceiling and the title text
(`isLimitedGame`, composing `hasRestrictedLabel`), kept free of DOM access so it
is unit-tested directly; small DOM helpers read the attributes off a row.

**Presentation** flags limited games in two places:

- in the games list, by dimming the row (cell-level opacity, robust to the
  site's own cell text colors) and adding a quiet "Limited" badge, so the game
  recedes before the user clicks reserve (the primary prevention point). Dimming
  the rare limited game reads better than emphasizing it; the badge's text
  labels why the row is dimmed without re-brightening it, so the signal never
  rests on color alone. The site shows the date on a day's first game and hides
  it on the rest, so the first game's date heads the whole day. That date cell
  (the one carrying the day-of-week label) is excluded from the dimming, so a
  limited first game does not dim the date the open games below rely on; and
- in the reservation modal, by a warning banner shown when the modal opens for a
  limited game (a second catch right before saving). The modal carries no
  ceiling of its own, so its limited status is carried over from the list: a
  click on a limited game's reserve button is remembered and consumed when the
  modal opens.

## Hard parts and risks

- **Name autocomplete (trickiest piece).** The name fields bind a player record
  (an ACBL/player id) behind the visible text, set when a user picks an entry
  from the site's autocomplete dropdown — not from free text. The chosen
  approach is to simulate that human interaction as faithfully as possible: set
  the name, dispatch the input events that open the dropdown, and select the
  matching entry, letting the site perform its own binding. This applies to the
  reserve flow; the My Reservations field is filled with text only and left
  unselected, since selecting there submits the lookup rather than advancing to
  the next field. Either way the field must be focused before the value is set:
  the site opens its dropdown only for the focused field, so an unfocused fill
  leaves the name in place with no entry to pick — the reserve modal focuses its
  own name field on open, but the My Reservations modal does not. This keeps the
  stored profile to just the name for identity — no need to replicate the site's
  internal id/contact data. Text-fill is the fallback if the dropdown can't be
  driven reliably, accepting one manual click to confirm. Verification must
  confirm a reservation actually persists with the correct player, not merely
  that the field shows the right name.
- **Asynchronously rendered DOM.** Elements (and especially modal dialogs)
  appear after initial load and after user actions. Features must wait for their
  targets — a shared "run when this selector appears" helper built on
  `MutationObserver` — rather than assuming elements exist at script start.
- **Modal lifecycle.** The reserve, My Reservations, and cancel modals are
  mounted once and shown on demand rather than created per use — all three sit
  in the DOM from page load, empty. Prefills and the warning banner must
  therefore react to a modal _opening_, not to its insertion (which happened at
  load): hooking insertion alone would fire once, against an empty modal, and
  never again. The site builds its modals two ways, so there is one open hook
  per mechanism: `onPopoverOpened` watches a `[popover]` element's `toggle`
  event (the reserve and My Reservations modals), and `onDialogOpened` watches a
  `<dialog>`'s `open` attribute (the cancel modal). Which mechanism a given
  modal uses is the site's choice and can change, so a modal is addressed by its
  own id rather than by element type — matching every `<dialog>` on the page
  would sweep in the site's unrelated ones.
- **Limited-banner carry-over flag.** The reserve modal has no masterpoint
  ceiling, so its limited status rides a single flag, set when a limited game's
  reserve button is clicked and consumed at the next modal open. If that click
  never opens the modal (the game has already started, say), the flag lingers
  and the next reserve — even of an open game — shows a spurious banner.
  Accepted as low-probability and low-harm (an extra, dismissable warning)
  rather than threading per-game state through the DOM.

## Architecture

A single userscript file, organized as:

- the userscript metadata header (`@match` the reservations URL; `@grant` the
  `GM_*` storage functions);
- the MIT license block;
- profile storage accessors over `GM_setValue`/`GM_getValue`;
- the in-page settings panel;
- shared helpers: "run when selector appears" (`MutationObserver`-based) and the
  two modal-open hooks, one per modal mechanism the site uses;
- `isLimitedGame` — the pure limited-game detector (over a game's masterpoint
  ceiling);
- one feature module per convenience above, each wiring its behavior to the
  appropriate page-ready or modal-open trigger.

## Testing strategy {#testing-strategy}

Three tiers, matched to how testable each piece is.

- **Unit tests for pure logic.** `isLimitedGame` (a game is limited when it
  carries a masterpoint ceiling, open when it carries none) is pure and testable
  without a browser — the cheapest, highest-value coverage.
- **jsdom tests for deterministic DOM features.** Row flagging, the "Show more
  games" expansion, the section default, and the value-setting prefills are
  deterministic transformations of the page, testable under a Node toolchain
  (vitest + jsdom): build minimal synthetic markup inline, hand it to the
  feature, assert the DOM change. Each test inlines the small fragment it needs
  rather than loading a shared capture.

- **jsdom tests for the page wiring**, run against fragments shaped like the
  live page. The tier above hands each feature the element it operates on, which
  leaves `main()`'s selectors — the only place this project's logic meets the
  site — never exercised at all. That gap is not hypothetical: a site change
  once removed a row attribute and moved a modal from `<dialog>` to `[popover]`,
  killing three features outright while every feature-level test stayed green,
  because none of them ever asked the page for an element.

  So these tests run the real `main()` and assert the feature reached its
  target, and their fixtures carry the live markup's shape — the attributes a
  row really has, the wrappers really around a control — rather than the minimum
  each feature reads. A fixture trimmed to what the code already looks at cannot
  fail when the code looks in the wrong place. `main()` returns its observers
  for this tier's sake, so a test can disconnect what it wired.

  Raw HTML captured from the live site was the original reference for the
  selectors and markup shape, but it held member PII, so it was gitignored and
  has since been deleted — re-capture from the live site if ever needed. Because
  every fixture still encodes our reading of a site we do not control, passing
  tests prove the logic is internally consistent and the selectors agree with
  the shape we recorded — never that the live markup still has that shape.

- **A scripted run against the live site** (`verify_live.py`) for what the tiers
  above can't reach: whether the live markup still matches the structure the
  tests assume. It injects the userscript into a real browser, drives each
  convenience, and reports which ones still fire — so a site change is diagnosed
  in one run rather than feature by feature. It stays out of `run_tests.sh`,
  since it needs the network and a site whose contents change daily, and it
  writes no page markup to disk: the live page carries other members' names
  throughout.

  Booking something by accident is the one unacceptable failure, so the script
  is built to make that impossible rather than merely unlikely. It clicks no
  save control, and underneath that a request guard allowlists the site's lookup
  calls and refuses everything else. The allowlist is what makes the guard
  fail-closed: the site funnels reads and writes alike through a single
  `POST action.php` distinguished by an `action` field, so blocking by HTTP
  method cannot separate them, and any action the script does not name — every
  save among them — is refused.

- **Manual in-browser verification** for the last stretch the scripted run can't
  reach: the name autocomplete binding depends on the site's own JS event
  handling, and confirming it goes one step past appearance — complete a
  reservation and confirm it persists against the correct player record. The
  scripted run checks that the field carries a bound player id, which is a proxy
  for this, not a substitute. One trap when driving the page from a
  browser-automation tool: `new-reserve-button` defines its own `click()`, which
  opens the reserve modal directly without dispatching a click event, so a
  scripted `element.click()` silently skips every click listener — including the
  one that arms the limited-game banner. Only a real mouse click exercises that
  path.

## Type checking

The goal is static type safety over the userscript without surrendering its
defining constraint — a single hand-written file the user copies into
Tampermonkey, with no build step and no generated artifact (see "Platform and
packaging"). Real TypeScript fails that test: `.ts` must be compiled to `.js`,
reintroducing a build and a derived file to keep in sync.

The chosen path keeps the source a plain `.js` and checks it in place:

- `// @ts-check` at the top of the userscript opts the file into the TypeScript
  checker; types are expressed in JSDoc, which the browser ignores as comments.
- `jsconfig.json` turns on `checkJs` and `strict`, so the check runs under
  `tsc --noEmit` (no output, pure verification) and the editor.
- `globals.d.ts` declares the globals that have no source here: Tampermonkey's
  `GM_*` storage API (present only in the userscript host) and Node's `module`
  (present only under vitest, for the test seam).

The `GM_*` and `module` globals are each guarded by a `typeof … !== "undefined"`
check at runtime, so the same file runs unmodified in both hosts; the ambient
declarations let the checker see both.

DOM access carries the one recurring friction: `querySelector` is typed to
return the base `Element`, but the code reaches for subtype members (`.value`,
`.dataset`, an option's `.selected`). The site-owned lookups go through
`querySelectorOfType`, which narrows with a runtime `instanceof` instead of an
unchecked cast: a present-but-wrong-type match (the site changing its markup out
from under a selector) is caught at runtime and logged, where a bare cast would
let it pass silently. `onElementAdded` and `findByText` are generic over the
element type, so a caller's callback or lookup fixes the subtype once. A JSDoc
cast remains only where `instanceof` cannot reach — a generic type parameter, an
event subtype, or an element this code just constructed.

The check is gated ahead of the tests in the repo-root `run_tests.sh`: a type
error fails the run before vitest starts.

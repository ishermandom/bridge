# Palo Alto reservations helper — tasks

Design record: `spec.md`.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

**Fixtures.** Raw HTML captures from the live site (`fixtures/raw/`) were the
build-time reference for selectors and markup shape. They held real member PII,
so they were gitignored and have since been deleted — re-capture from the live
site if ever needed. The committed jsdom tests don't depend on them: each
inlines its own minimal synthetic markup. The selectors and the
name-autocomplete recipe now live inline in `pabc-reservations.user.js` and in
`spec.md`.

## Scaffold

**Goal:** project skeleton and JS toolchain in place.

Done: userscript skeleton (`pabc-reservations.user.js`) and JS toolchain
(`package.json`, vitest + jsdom).

Done: repo-root `run_tests.sh` (runs the palo_alto vitest suite via
`npm --prefix`, no `cd`). A Stop test-hook can call this script.

---

## Type checking

**Goal:** static type checking for the userscript with no build step.

- [ ] Adopt `// @ts-check` + JSDoc type-checking (preserves the no-build,
      single-file packaging). Add a `jsconfig.json` with `checkJs`, plus ambient
      declarations for the `GM_*` globals and the `module` test seam, then
      resolve the type errors that surface.
  - Rationale: real TypeScript needs compilation, reintroducing a build and a
    generated artifact; `@ts-check` gives editor and `tsc --noEmit` checking
    over the `.js` in place — most of the benefit, none of the build.

---

## Core infrastructure ✓

**Goal:** storage, settings UI, and shared DOM helpers the features build on.

Done: profile storage (`loadProfile`/`saveProfile` over `GM_*`), the
`onElementAdded` MutationObserver helper, and the in-page settings panel — all
with jsdom tests.

- Note: `onElementAdded` covers modals that mount into the DOM (cancel, lookup
  dialogs). The reserve popover toggles visibility instead of mounting, so its
  open-trigger is a `toggle` listener handled in the reserve feature.
- Note: settings panel styling is minimal/functional — a polish pass is
  deferred.

---

## Limited-game guard ✓

**Goal:** detect limited games and flag them visually (no interception).

Done: `isLimitedGame` detector (pure, unit-tested), the games-list flag
(`flagLimitedGame` — tinted row + "Limited" badge), and the reserve-dialog
warning banner (`showLimitedBanner`, reading sections from `#sectionMenu`) —
with jsdom tests.

---

## Prefills and page tweaks ✓

**Goal:** the remember-me conveniences. Prefills fill only empty/default fields
— never overwriting what the user has typed or chosen.

Done, all with jsdom tests: show-more expansion, direction default, section
default to "Open", cancel-email prefill, and the name-autocomplete simulation
(`fillNameField`/`selectDropdownMatch`) used by both the reserve and lookup
fields.

- Note: the name autocomplete (#autocomplete) is exercised in jsdom only against
  a pre-seeded dropdown — jsdom can't run the site's own JS, so the actual
  dropdown population and player-record binding are unproven until the live
  pass. Text-fill is the fallback if the dropdown can't be driven. See spec
  ("Hard parts").

---

## Verify ✓

**Goal:** confirm behavior against the live site.

Done (live, by the user): prefills (reserve name/direction, lookup name, cancel
email), show-more, dimming + "Limited" flag on the correct games, the
reserve-dialog banner, fireworks suppression, and — the key check — a
reservation persisting with the correct player record. Section default left
unverified (the site already defaults to "Open"); the prefill is harmless if so.

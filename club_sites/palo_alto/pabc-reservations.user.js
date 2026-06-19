// ==UserScript==
// @name         PABC reservations helper
// @namespace    https://paloaltobridge.org/
// @description  Conveniences for the Palo Alto Bridge Center reservations page.
// @match        https://paloaltobridge.org/reservations/*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// @version      1.0
// ==/UserScript==

// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

"use strict";

// --- Limited-game detection ------------------------------------------------
//
// Pure, DOM-free classification, so it is unit-testable on its own. A game is
// "limited" when its eligibility could bar the user. Two independent signals,
// either sufficient:
//   1. a masterpoint ceiling on the row's `data-mps` (e.g. EZ Bridge at 49) —
//      but the site populates this inconsistently, carrying it on some
//      instances of an event and not others, so it cannot stand alone; and
//   2. a restriction named in the game's title/subtitle (`data-name` +
//      `data-special`): a beginner/NLM/Mid-Flight label, or a masterpoint cap
//      like "0-3000MP" or "0-99".
// The title text is checked, not the section list, because sections are
// overloaded — an open stratified game lists a "<500MP" section yet is open to
// all through its "Open" section, and session/bracket logistics ("Morning
// only", "Bracketed teams") share the same field. See spec.md ("Limited-game
// guard").

// Phrases that name a limited game in its title or subtitle.
const RESTRICTED_LABELS = ["ez bridge", "non-life master", "nlm", "mid-flight"];

/**
 * True if a game's title/subtitle names an eligibility restriction — a known
 * limited-game label, or a masterpoint cap like "0-3000MP" or "0-99".
 *
 * @param {string} label - the game's `data-name` and `data-special`, combined.
 * @returns {boolean}
 */
function hasRestrictedLabel(label) {
  const text = label.toLowerCase();

  if (RESTRICTED_LABELS.some((restriction) => text.includes(restriction))) {
    return true;
  }

  // Masterpoint caps phrased in the title, built from named parts since JS has
  // no verbose-regex mode: a "0-99"/"0-3000" range, or a "<500MP" ceiling.
  const cappedRange = String.raw`0\s*-\s*\d+`;
  const cappedCeiling = String.raw`<\s*\d+\s*mp`;
  const masterpointCapPattern = new RegExp(`${cappedRange}|${cappedCeiling}`);
  return masterpointCapPattern.test(text);
}

/**
 * True if a game's eligibility could bar the user — it carries a masterpoint
 * ceiling, or its title names a restriction. Either signal suffices.
 *
 * @param {?number} masterpointCeiling - MP cap from `data-mps`, or null.
 * @param {string} label - the game's title and subtitle, combined.
 * @returns {boolean}
 */
function isLimitedGame(masterpointCeiling, label) {
  const hasCeiling =
    typeof masterpointCeiling === "number" && masterpointCeiling > 0;
  return hasCeiling || hasRestrictedLabel(label);
}

// --- Profile storage -------------------------------------------------------
//
// The remembered identity, held in Tampermonkey's per-script storage (never
// sent to the site except through the forms the user submits). See spec.md
// ("Profile model and storage", "Security model").

const PROFILE_KEY = "profile";

// `direction` is one of the site's direction values ("", "N-S", "E-W");
// default to East/West per the user's preference.
const DEFAULT_PROFILE = {
  name: "",
  email: "",
  direction: "E-W",
};

/**
 * The stored profile, with defaults filled in for any absent field.
 */
function loadProfile() {
  return { ...DEFAULT_PROFILE, ...GM_getValue(PROFILE_KEY, {}) };
}

/**
 * Persist the profile, normalized against the defaults.
 */
function saveProfile(profile) {
  GM_setValue(PROFILE_KEY, { ...DEFAULT_PROFILE, ...profile });
}

// --- DOM helpers -----------------------------------------------------------

/**
 * Run `callback` once for each element matching `selector` — those present now
 * and any added later. The page renders much of its content (and its modals)
 * asynchronously, so a feature cannot assume its target exists at startup.
 *
 * @returns {MutationObserver} the observer, so a caller can disconnect it.
 */
function onElementAdded(selector, callback) {
  const seen = new WeakSet();

  // Scan the whole document for matches not yet handled. Matching against the
  // document — rather than each added subtree in isolation — correctly handles
  // a descendant selector even when an added subtree's own root is the
  // selector's leading element (e.g. a `<dialog>` mounted whole, for a
  // `dialog .inputDiv input` selector); a per-subtree `querySelectorAll` would
  // look for a nested second `<dialog>` and miss the field.
  const scan = () => {
    for (const element of document.querySelectorAll(selector)) {
      if (!seen.has(element)) {
        seen.add(element);
        callback(element);
      }
    }
  };

  scan();

  const observer = new MutationObserver((mutations) => {
    const hasAddedElement = mutations.some((mutation) =>
      [...mutation.addedNodes].some(
        (node) => node.nodeType === Node.ELEMENT_NODE,
      ),
    );
    if (hasAddedElement) {
      scan();
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  return observer;
}

/**
 * Run `callback(dialog)` each time `dialog` opens — at once if it is already
 * open, and on every later open. A `<dialog>` is mounted once and shown on
 * demand (its `open` attribute appearing), so a feature that fills it must
 * react to the opening, not to the element being inserted — it may have
 * existed, empty, since page load.
 *
 * @returns {MutationObserver} the observer, so a caller can disconnect it.
 */
function onDialogOpened(dialog, callback) {
  const handleIfOpen = () => {
    if (dialog.open) {
      callback(dialog);
    }
  };

  handleIfOpen();

  // `showModal()`/`show()` and the bare attribute all reflect `open`.
  const observer = new MutationObserver(handleIfOpen);
  observer.observe(dialog, { attributes: true, attributeFilter: ["open"] });
  return observer;
}

// --- Settings panel --------------------------------------------------------
//
// The only writer of the stored profile: a gear button that toggles a small
// editor for name, email, and direction.

const DIRECTION_OPTIONS = [
  { value: "", label: "No preference" },
  { value: "N-S", label: "North/South" },
  { value: "E-W", label: "East/West" },
];

/**
 * A labeled `<input>` appended to `panel`. Returns the input.
 */
function appendField(panel, labelText, type, value) {
  const label = document.createElement("label");
  label.textContent = `${labelText}: `;

  const input = document.createElement("input");
  input.type = type;
  input.value = value;

  label.append(input);
  panel.append(label);
  return input;
}

/**
 * A grouped set of direction radio buttons appended to `panel`, with the stored
 * direction checked. Radios read unambiguously as a choice. A native `<select>`
 * rendered here as flat text (the site appears to restyle selects, wrapping its
 * own in `<menu-frame>` overlays and suppressing the native affordance), so
 * radios sidestep that. Returns the fieldset; read its checked radio.
 */
function appendDirectionField(panel, value) {
  const fieldset = document.createElement("fieldset");

  const legend = document.createElement("legend");
  legend.textContent = "Direction";
  fieldset.append(legend);

  for (const { value: optionValue, label: optionLabel } of DIRECTION_OPTIONS) {
    const label = document.createElement("label");

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "pabcDirection";
    radio.value = optionValue;
    radio.checked = optionValue === value;

    label.append(radio, ` ${optionLabel}`);
    fieldset.append(label);
  }

  panel.append(fieldset);
  return fieldset;
}

/**
 * The helper's own styles — the settings gear and panel, plus the limited-game
 * row dimming, badge, and reserve-dialog banner. Injected once.
 */
function injectHelperStyles() {
  if (document.getElementById("pabcHelperStyles")) {
    return;
  }

  const style = document.createElement("style");
  style.id = "pabcHelperStyles";
  style.textContent = `
    #pabcHelperGear {
      position: fixed; right: 1rem; bottom: 1rem; z-index: 9999;
      width: 2.5rem; height: 2.5rem; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      padding: 0; line-height: 1; font-size: 1.8rem; cursor: pointer;
    }
    #pabcHelperSettings {
      position: fixed; right: 1rem; bottom: 4rem; z-index: 9999;
      display: flex; flex-direction: column; gap: 0.5rem; padding: 1rem;
      background: #fff; border: 1px solid #ccc; border-radius: 0.5rem;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }
    #pabcHelperSettings[hidden] { display: none; }
    /* The direction radios read as an obvious grouped control. */
    #pabcHelperSettings fieldset {
      margin: 0; padding: 0.4rem 0.6rem;
      border: 1px solid #ccc; border-radius: 0.25rem;
    }
    #pabcHelperSettings fieldset label {
      display: block; font-weight: normal;
    }

    /* A limited game's row recedes (it's the rare case the user usually wants
       to skip). Dimming is cell-level opacity, not a text color, so the site's
       own cell colors can't override it — and it fades the badge along with the
       row. The "Limited" badge is a quiet neutral tag that labels why the row
       is dimmed rather than a bright alert that fights the dimming. */
    tr.pabc-limited > td { opacity: 0.4; }
    /* align-self/fit-content keep the chip hugging its text — the name cell is
       a flex column, which would otherwise stretch the chip to the cell's
       width. */
    .pabc-limited-badge {
      display: inline-block; align-self: flex-start; width: fit-content;
      margin-top: 0.15rem; padding: 0 0.4rem;
      font-size: 0.75rem; font-weight: 600;
      color: #555; background: #e2e2e2; border-radius: 0.25rem;
    }
    /* Cosmetics only — the banner's layout (text wrap, width cap, centering) is
       set inline in showLimitedBanner with !important, to beat the site's
       higher-specificity rules on the dialog's children. */
    .pabc-reserve-banner {
      box-sizing: border-box; padding: 0.5rem 0.75rem; font-weight: 600;
      color: #856404; background: #fff3cd;
      border: 1px solid #ffeeba; border-radius: 0.25rem;
    }

    /* The Firecracker sectional spawns <firework-element> animations
       (js/Firework.js). These start out looking kind of like an insect crawling
       across the screen; suppress them. */
    firework-element { display: none !important; }
  `;
  document.head.append(style);
}

/**
 * Inject the settings UI and return its gear and panel elements.
 */
function mountSettingsPanel(root = document.body) {
  injectHelperStyles();

  const profile = loadProfile();

  const panel = document.createElement("form");
  panel.id = "pabcHelperSettings";
  panel.hidden = true;

  const nameInput = appendField(panel, "Name", "text", profile.name);
  const emailInput = appendField(panel, "Email", "email", profile.email);
  const directionField = appendDirectionField(panel, profile.direction);

  const saveButton = document.createElement("button");
  saveButton.type = "submit";
  saveButton.textContent = "Save";
  panel.append(saveButton);

  panel.addEventListener("submit", (event) => {
    event.preventDefault();
    saveProfile({
      name: nameInput.value.trim(),
      email: emailInput.value.trim(),
      direction: directionField.querySelector("input:checked")?.value ?? "",
    });
    panel.hidden = true;
  });

  const gear = document.createElement("button");
  gear.id = "pabcHelperGear";
  gear.type = "button";
  gear.textContent = "⚙";
  gear.title = "Reservations helper settings";
  gear.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
  });

  root.append(gear, panel);
  return { gear, panel };
}

// --- Limited-game flag -----------------------------------------------------

/**
 * The masterpoint ceiling on a game row's `data-mps`, or null when absent.
 *
 * @param {Element} row - a game `<tr>`.
 * @returns {?number}
 */
function parseMasterpointCeiling(row) {
  const raw = row.dataset.mps;
  if (raw == null || raw === "") {
    return null;
  }

  const ceiling = Number(raw);
  if (!Number.isFinite(ceiling)) {
    // A present-but-non-numeric ceiling means the site changed its encoding;
    // surface it (rather than fail silently) and treat the game as open.
    console.warn("PABC helper: non-numeric data-mps", raw);
    return null;
  }
  return ceiling;
}

/**
 * Dim a limited game's row and badge its name. No-op for an open game.
 *
 * @returns {boolean} whether the row was flagged.
 */
function flagLimitedGame(row) {
  const label = `${row.dataset.name ?? ""} ${row.dataset.special ?? ""}`;
  if (!isLimitedGame(parseMasterpointCeiling(row), label)) {
    return false;
  }

  row.classList.add("pabc-limited");

  const gameName = row.querySelector(".gameName");
  if (gameName && !gameName.querySelector(".pabc-limited-badge")) {
    const badge = document.createElement("span");
    badge.className = "pabc-limited-badge";
    badge.textContent = "Limited";
    gameName.append(badge);
  }

  return true;
}

/**
 * Show or remove the reserve modal's limited-game warning banner — a second
 * catch right before saving. The caller supplies the limited status, since the
 * modal itself carries no masterpoint ceiling (it is read from the originating
 * game row). Returns the banner, or null when none is shown.
 *
 * @param {Element} modal - the reserve popover (`#newReservation`).
 * @param {boolean} isLimited - whether the game being reserved is limited.
 */
function showLimitedBanner(modal, isLimited) {
  const existing = modal.querySelector(".pabc-reserve-banner");

  if (!isLimited) {
    if (existing) {
      existing.remove();
    }
    return null;
  }

  if (existing) {
    return existing;
  }

  const banner = document.createElement("div");
  banner.className = "pabc-reserve-banner";
  banner.textContent =
    "Limited game — restricted eligibility. Reserve only if you mean to.";

  // The site's dialog-child CSS out-specifies our class — it forces the text
  // onto one line, so the banner overflows the dialog. Set the layout inline
  // with !important, which a site selector rule cannot override: wrap the text,
  // cap the width, and center it within the (wider) form. Cosmetics stay in the
  // stylesheet, which the site does not override.
  banner.style.setProperty("white-space", "normal", "important");
  banner.style.setProperty("max-width", "18rem", "important");
  banner.style.setProperty("margin", "0 auto 0.75rem", "important");

  modal.prepend(banner);
  return banner;
}

// --- Prefills and page tweaks ----------------------------------------------
//
// Each prefill fills only an empty field or a control still at its default, so
// it never overwrites what the user has already typed or chosen.

/**
 * Expand the collapsed game list so every game is visible on load.
 */
function expandShowMore(button) {
  // The same control toggles to "Show less" once expanded; only click while it
  // still offers "more", so a re-run never collapses the list.
  if (button.textContent.toLowerCase().includes("more")) {
    button.click();
  }
}

/**
 * Pre-select the stored direction when the reserve modal's direction control is
 * still at its "No preference" default.
 */
function prefillDirection(modal, direction) {
  const select = modal.querySelector("#direction");
  if (select && direction && select.value === "") {
    select.value = direction;
  }
}

/**
 * Default the reserve modal's section dropdown to "Open" when it is still at
 * its first option. Harmless when the game has no "Open" section.
 */
function prefillSection(modal) {
  const menu = modal.querySelector("#sectionMenu");
  if (!menu || menu.selectedIndex !== 0) {
    return;
  }

  const open = [...menu.options].find(
    (option) => option.textContent.trim().toLowerCase() === "open",
  );
  if (open) {
    open.selected = true;
  }
}

/**
 * Prefill the cancellation flow's confirmation email when the field is empty.
 */
function prefillCancelEmail(input, email) {
  if (input && email && input.value.trim() === "") {
    input.value = email;
  }
}

// --- Name autocomplete -----------------------------------------------------
//
// The name fields bind a player record behind the visible text, set when the
// site's dropdown entry is picked — not from free text. So a prefill simulates
// the human flow: type the name, wait for the site to populate its dropdown,
// then click the matching entry and let the site bind. See spec ("Hard parts").

/**
 * Click the dropdown entry exactly matching `name` (case-insensitive). Exact
 * match avoids selecting a different person who merely shares a surname.
 *
 * @returns {boolean} whether a matching entry was found and clicked.
 */
function selectDropdownMatch(dropdown, name) {
  const target = name.trim().toLowerCase();
  const match = [...dropdown.querySelectorAll("li")].find(
    (item) => item.textContent.trim().toLowerCase() === target,
  );

  if (match) {
    match.click();
    return true;
  }
  return false;
}

/**
 * Poll `container` for a populated `ul.dropdown`, resolving with it once it has
 * entries, or with null if none appear before the timeout (the site changed, or
 * the name matched nobody) — in which case the typed text stands as a fallback.
 */
function waitForDropdownItems(container, timeoutMs = 2000, intervalMs = 50) {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;

    const poll = () => {
      const dropdown = container.querySelector("ul.dropdown");
      if (dropdown && dropdown.querySelector("li")) {
        resolve(dropdown);
        return;
      }
      if (Date.now() >= deadline) {
        resolve(null);
        return;
      }
      setTimeout(poll, intervalMs);
    };

    poll();
  });
}

/**
 * Type `name` into an autocomplete field — set the value and fire the input
 * event the site listens for — but only into an empty field, so a name the user
 * has already typed is left untouched. Does not select a dropdown entry, so it
 * never advances or submits the form.
 *
 * @returns {boolean} whether it typed.
 */
function typeName(input, name) {
  if (!input || !name || input.value.trim() !== "") {
    return false;
  }

  input.value = name;
  // The site opens its dropdown in response to input on the field.
  input.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

/**
 * Fill a name field and bind the player record by simulating the human flow:
 * type the name, wait for the site's dropdown, and click the matching entry so
 * the site binds the record. For flows where selecting advances the form
 * (reserving) — not the My Reservations dialog, where selecting submits and
 * closes it. If the dropdown never populates, the typed text stands for a
 * manual pick.
 *
 * @param {HTMLInputElement} input - the `.needsDropdown` name field.
 * @param {string} name - the stored full name.
 * @param {Element} container - the modal/dialog holding the field's dropdown.
 */
async function fillNameField(input, name, container) {
  if (!typeName(input, name)) {
    return;
  }

  const dropdown = await waitForDropdownItems(container);
  if (dropdown) {
    selectDropdownMatch(dropdown, name);
  }
}

// --- Page wiring -----------------------------------------------------------

// The reserve popover carries no masterpoint ceiling, so the limited status is
// carried over from the games list: a click on a limited game's reserve button
// sets this, and the next reserve-open consumes it to show the warning banner.
// Wiring-only state; the unit-tested feature functions take explicit arguments.
//
// Known tradeoff: if a limited game's reserve button is clicked but the popover
// never opens (e.g. the game is already reserved), the flag lingers and the
// next reserve-open — even of an open game — shows a spurious banner. Accepted
// as low-probability and low-harm (an extra, dismissable warning) rather than
// threading per-game limited state through the DOM. See spec ("Hard parts and
// risks").
let isPendingLimitedReserve = false;

/**
 * Run the reserve-flow features when the reserve popover opens: prefill
 * direction and section, warn on a limited game, and fill the player name.
 */
function onReserveOpen(modal) {
  const profile = loadProfile();
  prefillDirection(modal, profile.direction);
  prefillSection(modal);

  showLimitedBanner(modal, isPendingLimitedReserve);
  // Consume the flag so a later open of an open game shows no banner.
  isPendingLimitedReserve = false;

  const nameInput = modal.querySelector('input[name="player"]');
  // Fire-and-forget: the fill awaits the site's async dropdown; it never
  // rejects, and the reserve flow shouldn't block on it.
  void fillNameField(nameInput, profile.name, modal);
}

function main() {
  mountSettingsPanel();

  onElementAdded("#showMore", expandShowMore);

  // Flag limited game rows; on a limited row, remember a click on its reserve
  // button so the reserve modal can warn when it opens.
  onElementAdded("tr[data-sections]", (row) => {
    if (!flagLimitedGame(row)) {
      return;
    }
    const reserveButton = row.querySelector("new-reserve-button");
    if (reserveButton) {
      reserveButton.addEventListener("click", () => {
        isPendingLimitedReserve = true;
      });
    }
  });

  // Reserve popover toggles visibility rather than mounting, so its features
  // hang off the open event, not element insertion.
  onElementAdded("#newReservation", (modal) => {
    modal.addEventListener("toggle", (event) => {
      if (event.newState === "open") {
        onReserveOpen(modal);
      }
    });
  });

  // My Reservations dialog: a <dialog> with a needsDropdown name field, shown
  // on demand like the cancel dialog — fill the name when it opens, not when it
  // mounts. Only type the name (no dropdown click): on this dialog, selecting
  // an entry submits and closes it, and the user may want a different player.
  // The field is re-queried on open in case the site rebuilds it.
  onElementAdded("dialog", (dialog) => {
    onDialogOpened(dialog, () => {
      const nameInput = dialog.querySelector("input.needsDropdown");
      if (nameInput) {
        typeName(nameInput, loadProfile().name);
      }
    });
  });

  // Cancel dialog: the cancel-reservation-modal persists in the DOM and shows
  // its dialog on demand, so fill the email each time the dialog opens, not
  // when it mounts.
  onElementAdded("cancel-reservation-modal dialog", (dialog) => {
    onDialogOpened(dialog, () => {
      const input = dialog.querySelector(".inputDiv input");
      if (input) {
        prefillCancelEmail(input, loadProfile().email);
      }
    });
  });
}

// Run only as a userscript, where the GM storage API is present. Under Node
// (vitest) the GM functions are absent, so the page wiring never fires and the
// functions can be imported and tested in isolation.
if (typeof GM_getValue !== "undefined") {
  main();
}

// Test seam: expose functions to vitest without a build step. The `module`
// global is absent in the browser, so this is inert under Tampermonkey.
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    isLimitedGame,
    hasRestrictedLabel,
    loadProfile,
    saveProfile,
    onElementAdded,
    onDialogOpened,
    mountSettingsPanel,
    parseMasterpointCeiling,
    flagLimitedGame,
    showLimitedBanner,
    expandShowMore,
    prefillDirection,
    prefillSection,
    prefillCancelEmail,
    selectDropdownMatch,
    typeName,
    fillNameField,
  };
}

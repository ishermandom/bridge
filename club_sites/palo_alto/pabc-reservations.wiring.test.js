// @vitest-environment jsdom
// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// jsdom tests for the page wiring — `main()` run against page fragments shaped
// like the live site's.
//
// The other test files call each feature function directly, handing it the
// element it operates on. That leaves the selectors in `main()` untested, and
// the selectors are the only place this project's logic meets a site nobody
// here controls — so they are exactly what a site change breaks. These tests
// close that gap: they build the surrounding page, run the real wiring against
// it, and assert the feature reached its target.
//
// The fragments below therefore carry the live markup's shape — the attributes
// a row really has, the elements really wrapping a control — not the minimum
// each feature happens to read. A fixture trimmed to what the code already
// looks at cannot fail when the code looks in the wrong place. What these tests
// cannot do is notice the live page moving out from under the fixtures; that is
// `verify_live.py`'s job.

import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { main } from "./pabc-reservations.user.js";

const PROFILE = {
  name: "First Last",
  email: "first@example.com",
  direction: "E-W",
};

// Back the GM storage API with the profile every test reads through.
function installProfile() {
  const store = { profile: PROFILE };
  globalThis.GM_getValue = (key, fallback) =>
    key in store ? store[key] : fallback;
  globalThis.GM_setValue = (key, value) => {
    store[key] = value;
  };
}

// MutationObserver delivers on a microtask; let it flush.
function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/**
 * A games table holding one limited game (carrying a masterpoint ceiling) and
 * one open game, each with the reserve button the site puts in its last cell.
 * The open game's date cell carries `sameDate`, as it does live on every game
 * after a day's first.
 */
function makeGamesTable() {
  const table = document.createElement("table");
  table.innerHTML = `
    <tbody>
      <tr data-id="622" data-date="08/24/26" data-time="1115"
          data-name="EZ Bridge" data-special="" data-seating="1" data-mps="49">
        <td><div><span class="dow">Mon</span> Aug 24</div>
          <div class="timeCell">11:15am</div></td>
        <td>11:15am</td>
        <td><span class="tableFee">$15</span>
          <div class="gameName"><div>EZ Bridge </div>
            <div><span class="special"></span></div></div></td>
        <td><new-reserve-button title="Make a reservation"><div>Reserve</div>
          </new-reserve-button></td>
      </tr>
      <tr data-id="621" data-date="08/24/26" data-time="1130"
          data-name="Monday Morning Game" data-special="" data-seating="1">
        <td class="sameDate"><div><span class="dow">Mon</span> Aug 24</div>
          <div class="timeCell">11:30am</div></td>
        <td>11:30am</td>
        <td><span class="tableFee">$15</span>
          <div class="gameName"><div>Monday Morning Game </div>
            <div><span class="special"></span></div></div></td>
        <td><new-reserve-button title="Make a reservation"><div>Reserve</div>
          </new-reserve-button></td>
      </tr>
    </tbody>`;
  document.body.append(table);
}

// The row for a game by title, the way the wiring has to find it.
function gameRow(name) {
  return document.querySelector(`tr[data-name="${name}"]`);
}

/**
 * The reserve modal: a `[popover]` div whose selects sit inside the
 * `<menu-frame>` wrappers the site restyles them with, so the fixture exercises
 * a descendant lookup rather than a direct child.
 */
function makeReservePopover(sectionLabels = ["Open"]) {
  const modal = document.createElement("div");
  modal.id = "newReservation";
  modal.setAttribute("popover", "");
  modal.innerHTML = `
    <div class="headerDiv"><span class="new">New</span> reservation</div>
    <div id="dateDiv"></div>
    <div id="sectionDiv">Section: <menu-frame><select id="sectionMenu">
      ${sectionLabels.map((label) => `<option>${label}</option>`).join("")}
    </select><div class="transparent"></div></menu-frame></div>
    <div class="nameDiv">Name:
      <input name="player" autocomplete="off" class="needsDropdown"></div>
    <div class="nameDiv">Partner:
      <input name="partner" autocomplete="off" class="needsDropdown"></div>
    <div id="directionDiv"><label for="direction">Direction: </label>
      <menu-frame><select id="direction">
        <option value="">No preference</option>
        <option value="N-S">North/South</option>
        <option value="E-W">East/West</option>
      </select><div class="transparent"></div></menu-frame></div>
    <div id="saveDiv"><button value="save" class="saveButton">Save</button></div>
    <ul class="dropdown"></ul>`;
  document.body.append(modal);
  return modal;
}

// The My Reservations modal: also a `[popover]` div, and named "Dialog" by the
// site despite not being a `<dialog>` — the trap this fixture pins down.
function makeLookupPopover() {
  const modal = document.createElement("div");
  modal.id = "myReservationsDialog";
  modal.setAttribute("popover", "");
  modal.innerHTML = `
    <div class="headerDiv">My reservations</div>
    <div>Your name: <input class="needsDropdown"></div>
    <ul class="dropdown"></ul>`;
  document.body.append(modal);
  return modal;
}

// The cancellation modal — a real `<dialog>`, unlike the two above.
function makeCancelDialog() {
  const host = document.createElement("cancel-reservation-modal");
  host.innerHTML = `
    <dialog>
      <div class="message"></div>
      <div class="inputDiv"><input></div>
      <div><button value="OK">Cancel reservation</button>
        <button value="cancel">Keep</button></div>
    </dialog>`;
  document.body.append(host);
  return host.querySelector("dialog");
}

// jsdom implements neither the popover API nor `ToggleEvent`, so the event the
// browser would fire on `showPopover()` is synthesized.
function openPopover(modal) {
  const event = new Event("toggle");
  Object.defineProperty(event, "newState", { value: "open" });
  modal.dispatchEvent(event);
}

describe("page wiring", () => {
  let observers = [];

  beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    installProfile();
  });

  afterEach(() => {
    // These watch the whole document, so one left running would flag the next
    // test's rows.
    observers.forEach((observer) => observer.disconnect());
    observers = [];
    delete globalThis.GM_getValue;
    delete globalThis.GM_setValue;
  });

  test("expands the collapsed game list", () => {
    const button = document.createElement("button");
    button.id = "showMore";
    button.textContent = "▼ Show more games ▼";
    let clicks = 0;
    button.addEventListener("click", () => {
      clicks += 1;
    });
    document.body.append(button);

    observers = main();

    expect(clicks).toBe(1);
  });

  test("dims the limited game's row and leaves the open game's alone", () => {
    makeGamesTable();

    observers = main();

    expect(gameRow("EZ Bridge").classList.contains("pabc-limited")).toBe(true);
    expect(
      gameRow("Monday Morning Game").classList.contains("pabc-limited"),
    ).toBe(false);
  });

  test("badges the limited game's name cell", () => {
    makeGamesTable();

    observers = main();

    expect(
      gameRow("EZ Bridge").querySelector(".gameName .pabc-limited-badge"),
    ).not.toBeNull();
  });

  test("spares the date cell the day's other games read", () => {
    makeGamesTable();

    observers = main();

    const dateCell = gameRow("EZ Bridge").querySelector(".dow").closest("td");
    expect(dateCell.classList.contains("pabc-shared-cell")).toBe(true);
  });

  // Ordered before the limited-game case deliberately: the banner rides a
  // module-level flag, so a test that arms it must also consume it, and this
  // one would be the casualty of a leak.
  test("shows no warning when reserving an open game", () => {
    makeGamesTable();
    const modal = makeReservePopover();
    observers = main();

    gameRow("Monday Morning Game").querySelector("new-reserve-button").click();
    openPopover(modal);

    expect(modal.querySelector(".pabc-reserve-banner")).toBeNull();
  });

  test("warns when reserving a limited game", () => {
    makeGamesTable();
    const modal = makeReservePopover(["EZ Bridge players"]);
    observers = main();

    // A real click, as a person makes. The live element overrides `click()` to
    // open the modal without dispatching an event, which no scripted click can
    // reproduce — but a person's click does reach this listener.
    gameRow("EZ Bridge").querySelector("new-reserve-button").click();
    openPopover(modal);

    expect(modal.querySelector(".pabc-reserve-banner")).not.toBeNull();
  });

  test("prefills the stored direction when the reserve modal opens", () => {
    const modal = makeReservePopover();

    observers = main();
    openPopover(modal);

    expect(modal.querySelector("#direction").value).toBe("E-W");
  });

  test("defaults the section to Open when the reserve modal opens", () => {
    const modal = makeReservePopover(["EZ Bridge players", "Open"]);

    observers = main();
    openPopover(modal);

    expect(modal.querySelector("#sectionMenu").value).toBe("Open");
  });

  test("binds the player record when the reserve modal opens", async () => {
    const modal = makeReservePopover();
    // The site populates this list in response to the typed name; jsdom cannot
    // run the site's JS, so it is seeded and the click on it is the assertion —
    // that click is what binds the player record behind the visible text.
    modal.querySelector("ul.dropdown").innerHTML = "<li>First Last</li>";
    let picks = 0;
    modal.querySelector("ul.dropdown li").addEventListener("click", () => {
      picks += 1;
    });

    observers = main();
    openPopover(modal);
    await flush();

    expect(modal.querySelector('input[name="player"]').value).toBe(
      "First Last",
    );
    expect(picks).toBe(1);
  });

  test("prefills the name when the lookup modal opens", () => {
    const modal = makeLookupPopover();

    observers = main();
    openPopover(modal);

    expect(modal.querySelector("input.needsDropdown").value).toBe("First Last");
  });

  test("leaves the lookup modal's dropdown entry unselected", async () => {
    const modal = makeLookupPopover();
    modal.querySelector("ul.dropdown").innerHTML = "<li>First Last</li>";
    let picks = 0;
    modal.querySelector("ul.dropdown li").addEventListener("click", () => {
      picks += 1;
    });

    observers = main();
    openPopover(modal);
    await flush();

    // Assert the fill happened before asserting nothing was picked: on its own,
    // "nothing was picked" also holds when the wiring never ran at all, so it
    // would survive exactly the breakage these tests exist to catch.
    expect(modal.querySelector("input.needsDropdown").value).toBe("First Last");
    // Selecting here submits the lookup and closes the modal, and the user may
    // want to look up someone else.
    expect(picks).toBe(0);
  });

  test("prefills the email when the cancel dialog opens", async () => {
    const dialog = makeCancelDialog();
    observers = main();

    dialog.setAttribute("open", "");
    await flush();

    expect(dialog.querySelector(".inputDiv input").value).toBe(
      "first@example.com",
    );
  });
});

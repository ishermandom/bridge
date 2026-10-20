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
 * The game list, holding one day with a limited game and an open one. Only the
 * limited game's title marks it as limited: like the live EZ Bridge game, its
 * row carries no masterpoint ceiling.
 */
function makeGameList() {
  const list = document.createElement("div");
  list.id = "gameList";
  list.setAttribute("role", "list");
  list.innerHTML = `
    <div class="day today" data-date="08/24/26" data-dow="1" data-label="24">
      <div class="game" role="listitem" data-id="622" data-date="08/24/26"
          data-time="1115" data-dow="1" data-club="15" data-special=""
          data-name="EZ Bridge" data-tablefee="15" data-seating="1">
        <div class="dateCell"><div><span class="dow">Mon</span> Aug 24</div>
          <div class="phoneTime"><span>11:15am</span></div></div>
        <div class="timeCell"><span>11:15am</span></div>
        <div class="nameCell"><span class="tableFee">$15</span>
          <div class="gameName"><div>EZ Bridge </div>
            <div><span class="special"></span></div></div></div>
        <div class="actionCell">
          <reserve-button title="Make a reservation"><div>Reserve</div>
            </reserve-button>
          <partner-finder-button title="Need a partner"><div>Partner?</div>
            </partner-finder-button>
          <contact-button title="Contact director"><div>Director</div>
            </contact-button>
          <view-reservations title="View reservations"><div>View list</div>
            </view-reservations>
          <reservation-list>
            <div class="headerDiv"><span>Mon 08/24 EZ Bridge</span></div>
            <div class="chart"><div class="sectionBlock"
                data-section="EZ Bridge players" data-mps="49">
              <div class="sectionHeader">EZ Bridge players</div>
              <section-names class="sectionNames empty"></section-names>
            </div></div>
          </reservation-list>
        </div>
      </div>
      <div class="game" role="listitem" data-id="621" data-date="08/24/26"
          data-time="1130" data-dow="1" data-club="15" data-special=""
          data-name="Monday Morning Game" data-tablefee="15" data-seating="1">
        <div class="dateCell"><div><span class="dow">Mon</span> Aug 24</div>
          <div class="phoneTime"><span>11:30am</span></div></div>
        <div class="timeCell"><span>11:30am</span></div>
        <div class="nameCell"><span class="tableFee">$15</span>
          <div class="gameName"><div>Monday Morning Game </div>
            <div><span class="special"></span></div></div></div>
        <div class="actionCell">
          <reserve-button title="Make a reservation"><div>Reserve</div>
            </reserve-button>
          <partner-finder-button title="Need a partner"><div>Partner?</div>
            </partner-finder-button>
          <contact-button title="Contact director"><div>Director</div>
            </contact-button>
          <view-reservations title="View reservations"><div>View list</div>
            </view-reservations>
          <reservation-list>
            <div class="headerDiv"><span>Mon 08/24 Monday Morning Game</span>
              </div>
            <div class="chart"><div class="sectionBlock" data-section="Open"
                data-mps="">
              <div class="sectionHeader">Open</div>
              <section-names class="sectionNames empty"></section-names>
            </div></div>
          </reservation-list>
        </div>
      </div>
    </div>`;
  document.body.append(list);
}

// The row for a game by title, the way the wiring has to find it.
function gameRow(name) {
  return document.querySelector(`.game[data-name="${name}"]`);
}

// The opacity the helper's stylesheet gives an element: what the user sees as
// dimmed or not.
function opacityOf(element) {
  return getComputedStyle(element).opacity;
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
    makeGameList();

    observers = main();

    // The name rather than its cell: the calendar view lays the cell out with
    // `display: contents`, which draws no box for the cell's opacity to fade.
    expect(opacityOf(gameRow("EZ Bridge").querySelector(".gameName"))).toBe(
      "0.4",
    );
    expect(
      opacityOf(gameRow("Monday Morning Game").querySelector(".gameName")),
    ).toBe("1");
  });

  test("badges the limited game's name cell", () => {
    makeGameList();

    observers = main();

    expect(
      gameRow("EZ Bridge").querySelector(".gameName .pabc-limited-badge"),
    ).not.toBeNull();
  });

  test("spares the date cell the day's other games read", () => {
    makeGameList();

    observers = main();

    // Confirm the row dimmed before confirming its date did not: on its own,
    // "the date is bright" also holds when nothing was dimmed at all.
    const row = gameRow("EZ Bridge");
    expect(opacityOf(row.querySelector(".timeCell > span"))).toBe("0.4");
    expect(opacityOf(row.querySelector(".dateCell > div"))).toBe("1");
  });

  test("dims the limited game's buttons but not its reservation list", () => {
    makeGameList();

    observers = main();

    const row = gameRow("EZ Bridge");
    expect(opacityOf(row.querySelector("reserve-button"))).toBe("0.4");
    expect(opacityOf(row.querySelector("reservation-list"))).toBe("1");
  });

  test("shows no warning when reserving an open game", () => {
    makeGameList();
    const modal = makeReservePopover();
    observers = main();

    gameRow("Monday Morning Game").querySelector("reserve-button").click();
    openPopover(modal);

    expect(modal.querySelector(".pabc-reserve-banner")).toBeNull();
  });

  test("warns when reserving a limited game", () => {
    makeGameList();
    const modal = makeReservePopover(["EZ Bridge players"]);
    observers = main();

    // A real click, as a person makes. The live element overrides `click()` to
    // open the modal without dispatching an event, which no scripted click can
    // reproduce — but a person's click does reach this listener.
    gameRow("EZ Bridge").querySelector("reserve-button").click();
    openPopover(modal);

    expect(modal.querySelector(".pabc-reserve-banner")).not.toBeNull();
  });

  test("starts each wiring with no warning left pending", () => {
    makeGameList();
    observers = main();
    // Arm the pending warning and then never open the modal — the case that
    // leaves it set, since only an open consumes it.
    gameRow("EZ Bridge").querySelector("reserve-button").click();

    // Rebuild and rewire the page, as reloading it does.
    observers.forEach((observer) => observer.disconnect());
    document.body.innerHTML = "";
    const modal = makeReservePopover();
    observers = main();
    openPopover(modal);

    // A pending warning kept at module scope would outlive the reload and warn
    // about a game the user never chose.
    expect(modal.querySelector(".pabc-reserve-banner")).toBeNull();
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

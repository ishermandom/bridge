// @vitest-environment jsdom
// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// jsdom tests for the user-facing features as DOM transformations: limited-game
// flagging, the reserve-dialog banner, the prefills, and the name-autocomplete
// simulation.

import { describe, expect, test, vi } from "vitest";

import {
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
} from "./pabc-reservations.user.js";

// A game row with the given masterpoint ceiling (omitted = none) and title
// fields, plus a name cell for the badge.
function makeGameRow({ mps, name = "A Game", special = "" } = {}) {
  const table = document.createElement("table");
  const row = document.createElement("tr");
  if (mps != null) {
    row.dataset.mps = String(mps);
  }
  row.dataset.name = name;
  row.dataset.special = special;
  row.innerHTML = `<td><div class="gameName"><div>${name}</div></div></td>`;
  table.append(row);
  return row;
}

// A reserve popover whose section dropdown offers the given option labels.
function makeReserveModal(sectionLabels, directionValue = "") {
  const modal = document.createElement("div");
  modal.id = "newReservation";
  const menu =
    sectionLabels.length === 0
      ? ""
      : `<select id="sectionMenu">${sectionLabels
          .map((label) => `<option>${label}</option>`)
          .join("")}</select>`;
  modal.innerHTML = `
    <div class="headerDiv">reservation</div>
    ${menu}
    <input name="player" class="needsDropdown">
    <select id="direction">
      <option value="">No preference</option>
      <option value="N-S">North/South</option>
      <option value="E-W">East/West</option>
    </select>
    <ul class="dropdown" style="display: none;"></ul>`;
  modal.querySelector("#direction").value = directionValue;
  return modal;
}

describe("parseMasterpointCeiling", () => {
  test("reads a numeric ceiling from data-mps", () => {
    expect(parseMasterpointCeiling(makeGameRow({ mps: 49 }))).toBe(49);
  });

  test("returns null when the row has no ceiling", () => {
    expect(parseMasterpointCeiling(makeGameRow())).toBeNull();
  });

  test("warns and returns null for a non-numeric ceiling", () => {
    const row = makeGameRow();
    row.setAttribute("data-mps", "lots");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(parseMasterpointCeiling(row)).toBeNull();

    expect(warn).toHaveBeenCalled(); // an unreadable ceiling is surfaced
    warn.mockRestore();
  });
});

describe("flagLimitedGame", () => {
  test("dims the row and badges the name of a limited game", () => {
    const row = makeGameRow({ mps: 49 });

    expect(flagLimitedGame(row)).toBe(true);

    expect(row.classList.contains("pabc-limited")).toBe(true);
    expect(row.querySelector(".pabc-limited-badge").textContent).toBe(
      "Limited",
    );
  });

  test("flags a limited game named only in its title, with no ceiling", () => {
    const row = makeGameRow({
      name: "Firecracker Sectional",
      special: "Mid-Flight Pairs, 0-3000MP",
    });

    expect(flagLimitedGame(row)).toBe(true);
    expect(row.classList.contains("pabc-limited")).toBe(true);
  });

  test("leaves an open game untouched", () => {
    const row = makeGameRow();

    expect(flagLimitedGame(row)).toBe(false);

    expect(row.classList.contains("pabc-limited")).toBe(false);
    expect(row.querySelector(".pabc-limited-badge")).toBeNull();
  });

  test("marks the date cell shared so dimming skips it", () => {
    // The site shows the date on a day's first game and hides it on the rest,
    // so the first game's date heads the whole day. Dimming must skip that date
    // cell — the one carrying the day-of-week label — so it isn't dimmed.
    const row = makeGameRow({ mps: 49 });
    const dateCell = document.createElement("td");
    dateCell.innerHTML = `<div><span class="dow">Mon</span> Jun 22</div>`;
    row.prepend(dateCell);

    flagLimitedGame(row);

    expect(dateCell.classList.contains("pabc-shared-cell")).toBe(true);
    // The game's own name cell carries no date and still dims with the row.
    const gameCell = row.querySelector(".gameName").closest("td");
    expect(gameCell.classList.contains("pabc-shared-cell")).toBe(false);
  });

  test("does not add a second badge when run twice", () => {
    const row = makeGameRow({ mps: 49 });
    flagLimitedGame(row);
    flagLimitedGame(row);
    expect(row.querySelectorAll(".pabc-limited-badge")).toHaveLength(1);
  });
});

describe("showLimitedBanner", () => {
  test("adds a banner when the game is limited", () => {
    const modal = document.createElement("div");
    const banner = showLimitedBanner(modal, true);
    expect(banner).not.toBeNull();
    expect(modal.querySelector(".pabc-reserve-banner")).toBe(banner);
  });

  test("forces its wrapping layout inline, to beat the site's CSS", () => {
    const modal = document.createElement("div");
    const banner = showLimitedBanner(modal, true);
    // Inline + !important so the site's dialog-child rules can't suppress the
    // wrap and let the banner overflow.
    expect(banner.style.getPropertyValue("white-space")).toBe("normal");
    expect(banner.style.getPropertyPriority("white-space")).toBe("important");
  });

  test("adds no banner when the game is open", () => {
    const modal = document.createElement("div");
    expect(showLimitedBanner(modal, false)).toBeNull();
    expect(modal.querySelector(".pabc-reserve-banner")).toBeNull();
  });

  test("removes a stale banner when reopened for an open game", () => {
    const modal = document.createElement("div");
    showLimitedBanner(modal, true);
    showLimitedBanner(modal, false);
    expect(modal.querySelector(".pabc-reserve-banner")).toBeNull();
  });

  test("does not stack a second banner when run twice", () => {
    const modal = document.createElement("div");
    showLimitedBanner(modal, true);
    showLimitedBanner(modal, true);
    expect(modal.querySelectorAll(".pabc-reserve-banner")).toHaveLength(1);
  });
});

describe("expandShowMore", () => {
  test("clicks the button while it still offers 'more'", () => {
    const button = document.createElement("button");
    button.textContent = "▼ Show more games ▼";
    const clicked = vi.fn();
    button.addEventListener("click", clicked);
    expandShowMore(button);
    expect(clicked).toHaveBeenCalledTimes(1);
  });

  test("does not click once expanded, when the button reads 'less'", () => {
    const button = document.createElement("button");
    button.textContent = "▲ Show less games ▲";
    const clicked = vi.fn();
    button.addEventListener("click", clicked);
    expandShowMore(button);
    expect(clicked).not.toHaveBeenCalled();
  });
});

describe("prefillDirection", () => {
  test("sets the stored direction when the control is at its default", () => {
    const modal = makeReserveModal([], "");
    prefillDirection(modal, "E-W");
    expect(modal.querySelector("#direction").value).toBe("E-W");
  });

  test("leaves a direction the user already chose", () => {
    const modal = makeReserveModal([], "N-S");
    prefillDirection(modal, "E-W");
    expect(modal.querySelector("#direction").value).toBe("N-S");
  });

  test("fires a change event so the site registers the new direction", () => {
    const modal = makeReserveModal([], "");
    const select = modal.querySelector("#direction");
    const onChange = vi.fn();
    select.addEventListener("change", onChange);

    prefillDirection(modal, "E-W");

    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("prefillSection", () => {
  test("defaults to Open when it is offered and the menu is untouched", () => {
    const modal = makeReserveModal(["<500MP", "Open"]);
    prefillSection(modal);
    expect(modal.querySelector("#sectionMenu").value).toBe("Open");
  });

  test("leaves the menu alone when no Open section is offered", () => {
    const modal = makeReserveModal(["EZ Bridge players"]);
    prefillSection(modal);
    expect(modal.querySelector("#sectionMenu").selectedIndex).toBe(0);
  });

  test("does not override a section the user already moved off the default", () => {
    const modal = makeReserveModal(["Open", "<500MP", "<100MP"]);
    const menu = modal.querySelector("#sectionMenu");
    menu.selectedIndex = 2; // a deliberate choice away from the default option

    prefillSection(modal);

    expect(menu.selectedIndex).toBe(2);
  });

  test("fires a change event when it defaults to Open", () => {
    const modal = makeReserveModal(["<500MP", "Open"]);
    const menu = modal.querySelector("#sectionMenu");
    const onChange = vi.fn();
    menu.addEventListener("change", onChange);

    prefillSection(modal);

    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("prefillCancelEmail", () => {
  test("fills an empty confirmation field", () => {
    const input = document.createElement("input");
    prefillCancelEmail(input, "me@example.com");
    expect(input.value).toBe("me@example.com");
  });

  test("leaves an email the user already typed", () => {
    const input = document.createElement("input");
    input.value = "typed@example.com";
    prefillCancelEmail(input, "me@example.com");
    expect(input.value).toBe("typed@example.com");
  });
});

describe("selectDropdownMatch", () => {
  // Decoys that collide on a token with the target ("First Last"); only the
  // exact, case-insensitive full-name match should be clicked.
  function makeDropdown() {
    const dropdown = document.createElement("ul");
    dropdown.className = "dropdown";
    for (const name of ["Last First", "Other Last", "first last"]) {
      const item = document.createElement("li");
      item.textContent = name;
      dropdown.append(item);
    }
    return dropdown;
  }

  test("clicks the exact match, case-insensitively, not a surname sibling", () => {
    const dropdown = makeDropdown();
    const clicked = [];
    dropdown
      .querySelectorAll("li")
      .forEach((item) =>
        item.addEventListener("click", () => clicked.push(item.textContent)),
      );

    expect(selectDropdownMatch(dropdown, "First Last")).toBe(true);
    expect(clicked).toEqual(["first last"]);
  });

  test("returns false and clicks nothing when no entry matches", () => {
    const dropdown = makeDropdown();
    const clicked = vi.fn();
    dropdown
      .querySelectorAll("li")
      .forEach((item) => item.addEventListener("click", clicked));

    expect(selectDropdownMatch(dropdown, "Nobody Here")).toBe(false);
    expect(clicked).not.toHaveBeenCalled();
  });
});

describe("typeName", () => {
  test("types into an empty field and fires input, without selecting", () => {
    const input = document.createElement("input");
    const onInput = vi.fn();
    input.addEventListener("input", onInput);

    expect(typeName(input, "First Last")).toBe(true);

    expect(input.value).toBe("First Last");
    expect(onInput).toHaveBeenCalledTimes(1);
  });

  test("leaves a field the user already typed", () => {
    const input = document.createElement("input");
    input.value = "Someone Else";

    expect(typeName(input, "First Last")).toBe(false);

    expect(input.value).toBe("Someone Else");
  });
});

describe("fillNameField", () => {
  // A name field beside an already-populated dropdown, so the poll resolves at
  // once — jsdom can't run the site's JS, so the dropdown is pre-seeded here.
  function makeNameContainer() {
    const container = document.createElement("div");
    container.innerHTML = `
      <input name="player" class="needsDropdown">
      <ul class="dropdown">
        <li>Other Last</li>
        <li>first last</li>
      </ul>`;
    return container;
  }

  test("types the name and clicks the matching dropdown entry", async () => {
    const container = makeNameContainer();
    const input = container.querySelector("input");
    const matchingItem = container.querySelectorAll("li")[1];
    const clicked = vi.fn();
    matchingItem.addEventListener("click", clicked);

    await fillNameField(input, "First Last", container);

    expect(input.value).toBe("First Last");
    expect(clicked).toHaveBeenCalledTimes(1);
  });

  test("leaves a name the user already typed", async () => {
    const container = makeNameContainer();
    const input = container.querySelector("input");
    input.value = "Someone Else";
    const clicked = vi.fn();
    container
      .querySelectorAll("li")
      .forEach((item) => item.addEventListener("click", clicked));

    await fillNameField(input, "First Last", container);

    expect(input.value).toBe("Someone Else");
    expect(clicked).not.toHaveBeenCalled();
  });
});

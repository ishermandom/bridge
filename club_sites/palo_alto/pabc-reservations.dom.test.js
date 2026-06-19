// @vitest-environment jsdom
// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// jsdom tests for the storage and DOM-helper layer: profile storage over a
// mocked GM API, the MutationObserver-based element/dialog observers, and the
// settings panel.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  loadProfile,
  saveProfile,
  onElementAdded,
  onDialogOpened,
  mountSettingsPanel,
} from "./pabc-reservations.user.js";

// Back the GM storage API with a plain object for the duration of a test.
function installGMStorage() {
  const store = {};
  globalThis.GM_getValue = vi.fn((key, fallback) =>
    key in store ? store[key] : fallback,
  );
  globalThis.GM_setValue = vi.fn((key, value) => {
    store[key] = value;
  });
  return store;
}

function uninstallGMStorage() {
  delete globalThis.GM_getValue;
  delete globalThis.GM_setValue;
}

// MutationObserver delivers on a microtask; let it flush.
function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("profile storage", () => {
  let store;

  beforeEach(() => {
    store = installGMStorage();
  });
  afterEach(uninstallGMStorage);

  test("loadProfile returns defaults when nothing is stored", () => {
    expect(loadProfile()).toEqual({ name: "", email: "", direction: "E-W" });
  });

  test("saveProfile round-trips through storage", () => {
    saveProfile({
      name: "First Last",
      email: "firstlast@example.com",
      direction: "N-S",
    });
    expect(loadProfile()).toEqual({
      name: "First Last",
      email: "firstlast@example.com",
      direction: "N-S",
    });
  });

  test("loadProfile fills absent fields with defaults", () => {
    store.profile = { name: "First Last" };
    expect(loadProfile()).toEqual({
      name: "First Last",
      email: "",
      direction: "E-W",
    });
  });
});

describe("onElementAdded", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  test("fires for an element already present", () => {
    document.body.innerHTML = `<div class="target"></div>`;
    const callback = vi.fn();
    onElementAdded(".target", callback);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  test("fires for an element added later", async () => {
    const callback = vi.fn();
    onElementAdded(".target", callback);

    const element = document.createElement("div");
    element.className = "target";
    document.body.append(element);

    await flush();
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith(element);
  });

  test("fires for a match nested inside an added subtree", async () => {
    const callback = vi.fn();
    onElementAdded(".target", callback);

    const wrapper = document.createElement("section");
    wrapper.innerHTML = `<div class="target"></div>`;
    document.body.append(wrapper);

    await flush();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  test("does not fire twice for the same element", async () => {
    document.body.innerHTML = `<div class="target"></div>`;
    const callback = vi.fn();
    onElementAdded(".target", callback);

    // Re-parenting re-triggers the observer for an already-seen element.
    document.body.append(document.querySelector(".target"));

    await flush();
    expect(callback).toHaveBeenCalledTimes(1);
  });
});

describe("onDialogOpened", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  test("fires immediately when the dialog is already open", () => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.append(dialog);

    const callback = vi.fn();
    onDialogOpened(dialog, callback);

    expect(callback).toHaveBeenCalledTimes(1);
  });

  test("fires when a closed dialog later opens", async () => {
    const dialog = document.createElement("dialog");
    document.body.append(dialog);

    const callback = vi.fn();
    onDialogOpened(dialog, callback);
    expect(callback).not.toHaveBeenCalled();

    dialog.setAttribute("open", "");
    await flush();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  test("does not fire again when the dialog closes", async () => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.append(dialog);

    const callback = vi.fn();
    onDialogOpened(dialog, callback); // one call: already open at attach
    dialog.removeAttribute("open");
    await flush();

    expect(callback).toHaveBeenCalledTimes(1);
  });
});

describe("settings panel", () => {
  let store;

  beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    store = installGMStorage();
  });
  afterEach(uninstallGMStorage);

  test("gear toggles the panel open and closed", () => {
    const { gear, panel } = mountSettingsPanel();
    expect(panel.hidden).toBe(true);
    gear.click();
    expect(panel.hidden).toBe(false);
    gear.click();
    expect(panel.hidden).toBe(true);
  });

  test("populates fields from the stored profile", () => {
    store.profile = {
      name: "First Last",
      email: "firstlast@example.com",
      direction: "N-S",
    };
    const { panel } = mountSettingsPanel();
    expect(panel.querySelector('input[type="text"]').value).toBe("First Last");
    expect(panel.querySelector('input[type="email"]').value).toBe(
      "firstlast@example.com",
    );
    expect(
      panel.querySelector('input[name="pabcDirection"]:checked').value,
    ).toBe("N-S");
  });

  test("saving persists the edited profile and closes the panel", () => {
    const { gear, panel } = mountSettingsPanel();
    gear.click();

    panel.querySelector('input[type="text"]').value = " New Name ";
    panel.querySelector('input[type="email"]').value = "new@example.com";
    panel.querySelector('input[name="pabcDirection"][value="E-W"]').checked =
      true;
    panel.dispatchEvent(new Event("submit", { cancelable: true }));

    expect(store.profile).toEqual({
      name: "New Name",
      email: "new@example.com",
      direction: "E-W",
    });
    expect(panel.hidden).toBe(true);
  });
});

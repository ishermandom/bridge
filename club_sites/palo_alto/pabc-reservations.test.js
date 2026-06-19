// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Unit tests for the pure, DOM-free detection logic (isLimitedGame /
// hasRestrictedLabel). Runs in the default Node environment — no DOM needed.

import { describe, expect, test } from "vitest";

import { isLimitedGame, hasRestrictedLabel } from "./pabc-reservations.user.js";

describe("hasRestrictedLabel", () => {
  test("flags a named beginner / NLM / Mid-Flight restriction", () => {
    expect(hasRestrictedLabel("EZ Bridge")).toBe(true);
    expect(hasRestrictedLabel("Non-Life Master Regional")).toBe(true);
    expect(hasRestrictedLabel("NLM Gold Rush Pairs")).toBe(true);
    expect(hasRestrictedLabel("Mid-Flight Pairs")).toBe(true);
  });

  test("flags a masterpoint cap phrased in the title", () => {
    expect(hasRestrictedLabel("0-99 Pairs")).toBe(true);
    expect(hasRestrictedLabel("Mid-Flight Pairs, 0-3000MP")).toBe(true);
  });

  test("leaves an open game's title alone", () => {
    expect(hasRestrictedLabel("Thursday Bridge Club Championship")).toBe(false);
    expect(hasRestrictedLabel("Firecracker Sectional Open Pairs")).toBe(false);
    expect(hasRestrictedLabel("Firecracker Sectional Bracketed teams")).toBe(
      false,
    );
  });
});

describe("isLimitedGame", () => {
  test("flags a game with a masterpoint ceiling", () => {
    expect(isLimitedGame(49, "EZ Bridge")).toBe(true);
  });

  test("flags a restricted title even when the ceiling is absent", () => {
    // The site omits data-mps on some instances of a limited game, so the
    // title is the only signal left.
    expect(
      isLimitedGame(null, "Firecracker Sectional Mid-Flight Pairs, 0-3000MP"),
    ).toBe(true);
  });

  test("treats a game with no ceiling and an open title as open", () => {
    expect(isLimitedGame(null, "Thursday Bridge Club Championship")).toBe(
      false,
    );
  });
});

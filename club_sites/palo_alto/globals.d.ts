// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Ambient declarations for globals that exist at runtime but have no source in
// this project: the Tampermonkey GM_* storage API (present only in the
// userscript host) and Node's `module` (present only under vitest). Declaring
// them here lets `tsc --noEmit` check the single-file userscript without a
// build or any runtime shim. See spec.md ("Type checking").

/**
 * Read a stored value, returning `defaultValue` when the key is unset. The
 * return type follows the default, matching how the script reads its profile
 * object back out.
 */
declare function GM_getValue<T>(key: string, defaultValue: T): T;

/** Persist a value under `key`. */
declare function GM_setValue(key: string, value: unknown): void;

// The CommonJS `module`, present under Node (vitest) and absent in the browser.
// Optional so the userscript's `typeof module !== "undefined"` guard narrows it
// rather than tripping a "used before defined" check.
declare var module: { exports: Record<string, unknown> } | undefined;

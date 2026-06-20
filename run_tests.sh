#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Repo-wide test entry point. Runs each project's own suite. As more projects
# are added, append their invocations here.

# The repo root, so the script works regardless of the caller's directory.
repo_root="$(dirname "$0")"

# club_sites/palo_alto: a Tampermonkey userscript tested with vitest + jsdom.
package="$repo_root/club_sites/palo_alto"

# Type-check first, so a type error fails the run before vitest starts. `tsc`
# checks the JSDoc-annotated userscript in place — no build, no emit. Gating
# explicitly (rather than `&&`) keeps the failing step's own exit status.
npm --prefix "$package" run typecheck
typecheck_status=$?
if [ "$typecheck_status" -ne 0 ]; then
  exit "$typecheck_status"
fi

# `npm --prefix` runs that package's "test" script without changing directory.
exec npm --prefix "$package" test

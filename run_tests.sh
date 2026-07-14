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
# Gated explicitly, rather than `&&`, to keep the failing step's own exit status.
npm --prefix "$package" test
palo_alto_status=$?
if [ "$palo_alto_status" -ne 0 ]; then
  exit "$palo_alto_status"
fi

# session_analysis: a Python package tested with pytest, run through the uv
# workspace so it picks up the shared lockfile/venv regardless of the caller's
# directory. Pointing pytest at the package directory lets it insert the repo
# root on the import path, so the `session_analysis.*` imports resolve
# regardless of the caller's directory.
exec uv run --project "$repo_root" pytest "$repo_root/session_analysis"

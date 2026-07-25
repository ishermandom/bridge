#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Repo-wide test entry point. Runs each project's own suite. As more projects
# are added, append their invocations here — and have each block install
# whatever its own suite needs, so a fresh checkout runs green with no manual
# setup step.

# The repo root, so the script works regardless of the caller's directory.
repo_root="$(dirname "$0")"

# club_sites/palo_alto: a Tampermonkey userscript tested with vitest + jsdom.
package="$repo_root/club_sites/palo_alto"

# Install the Node dependencies when they're missing or older than the
# lockfile. npm doesn't bootstrap itself the way `uv run` below does, and
# node_modules is gitignored, so a fresh checkout — most often a new worktree —
# would otherwise reach `tsc` and `vitest` with neither on PATH. `ci` installs
# the lockfile exactly and fails on drift from package.json, where `install`
# would quietly rewrite it. The flags keep the common case fast and quiet:
# reuse the download cache, and skip the audit and funding reports.
node_modules="$package/node_modules"
if [ ! -d "$node_modules" ] \
  || [ "$package/package-lock.json" -nt "$node_modules" ]; then
  npm --prefix "$package" ci --prefer-offline --no-audit --no-fund
  install_status=$?
  if [ "$install_status" -ne 0 ]; then
    exit "$install_status"
  fi
fi

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

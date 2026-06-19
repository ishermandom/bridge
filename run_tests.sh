#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Repo-wide test entry point. Runs each project's own suite. As more projects
# are added, append their invocations here.

# The repo root, so the script works regardless of the caller's directory.
repo_root="$(dirname "$0")"

# club_sites/palo_alto: a Tampermonkey userscript tested with vitest + jsdom.
# `npm --prefix` runs that package's "test" script without changing directory.
exec npm --prefix "$repo_root/club_sites/palo_alto" test

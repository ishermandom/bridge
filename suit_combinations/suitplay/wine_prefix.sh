#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Creates Wine's settings folder for the machine's user, which Wine calls a
# prefix. Lima runs this as that user on every boot, after `setup.sh`, so it
# does nothing once the prefix exists.

prefix="$HOME/.wine"

# Stop with a message naming the step that failed.
fail() {
  echo "wine_prefix.sh: $1" >&2
  exit 1
}

if [ -d "$prefix" ]; then
  exit 0
fi
# Leaving out Wine's stand-ins for .NET and Internet Explorer skips the prompts
# to download them; SuitPlay needs neither.
DISPLAY=:1 WINEDLLOVERRIDES="mscoree,mshtml=" wineboot --init \
  || fail "creating the prefix failed"
# The prefix holds full copies of Wine's Windows libraries, over 2 GB. Hard
# links let each copy share disk space with its installed original. Those
# originals belong to root, so a later Hangover upgrade can't update the prefix
# in place; deleting the prefix lets this script build a fresh one.
sudo hardlink --content /usr/lib/wine "$prefix/drive_c/windows" > /dev/null \
  || fail "linking the prefix's copies failed"

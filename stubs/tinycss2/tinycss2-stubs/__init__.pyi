# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for tinycss2: only the surface this repo calls. See the README
# one level up before extending.

from collections.abc import Iterable

from tinycss2.ast import Node

def parse_stylesheet(
  input: str, skip_comments: bool = ..., skip_whitespace: bool = ...
) -> list[Node]: ...
def parse_blocks_contents(
  input: str | Iterable[Node],
  skip_comments: bool = ...,
  skip_whitespace: bool = ...,
) -> list[Node]: ...
def serialize(nodes: Iterable[Node]) -> str: ...

# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for genanki, covering only the API this repo calls. See
# `stubs/README.md` before extending.

import os
from collections.abc import Iterable, Sequence
from typing import TypedDict

class _Field(TypedDict):
  name: str

class _Template(TypedDict):
  name: str
  qfmt: str
  afmt: str

def guid_for(*values: object) -> str: ...

class Model:
  model_id: int
  name: str
  fields: list[_Field]
  templates: list[_Template]
  css: str
  def __init__(
    self,
    model_id: int,
    name: str,
    fields: list[_Field],
    templates: list[_Template],
    css: str = ...,
  ) -> None: ...

class Note:
  model: Model
  fields: Sequence[str]
  guid: str
  @property
  def tags(self) -> list[str]: ...
  def __init__(
    self,
    model: Model,
    fields: Sequence[str],
    tags: Iterable[str] = ...,
    guid: str = ...,
  ) -> None: ...

class Deck:
  deck_id: int
  name: str
  notes: list[Note]
  def __init__(self, deck_id: int, name: str) -> None: ...
  def add_note(self, note: Note) -> None: ...

class Package:
  def __init__(self, deck_or_decks: Deck) -> None: ...
  def write_to_file(self, file: str | os.PathLike[str]) -> None: ...

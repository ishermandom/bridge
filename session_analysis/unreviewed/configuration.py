# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The user-specific settings this pipeline reads rather than hard-codes.

Three values are particular to whoever runs this and stable across every run:
the name our row in a traveller is matched on, the ACBL player number both fetch
surfaces index a player's results by, and the club's own results calendar.
travellers.md `#configuration` settles what they are and why each is
configuration rather than code.

They are read from one TOML file in the private tree, never this repository, and
every setting is required — a file stating some of them is incomplete rather
than partial. travellers.md `#configuration` argues both choices.
"""

import tomllib
from typing import Annotated, BinaryIO

import pydantic

from session_analysis.frozen_model import FrozenModel
from session_analysis.private_paths import PrivateTree


class ConfigurationError(Exception):
  """The configuration is missing, unparseable, or incomplete.

  Purpose-built rather than a built-in: a caller catching this is offering to
  tell the person what to write, which is a different response than it would
  have to a malformed record anywhere else.
  """


# A setting written but left blank is not one its writer supplied, so it is
# rejected alongside one they never wrote at all. Left to stand it would fail
# far from here and in the wrong words: an empty name matches no row in any
# traveller, so every session would report that we appear nowhere in our own
# results rather than that the configuration is unfinished.
Setting = Annotated[
  str, pydantic.StringConstraints(strip_whitespace=True, min_length=1)
]


class Configuration(FrozenModel):
  """What this pipeline needs to know about the person running it."""

  # In full, as the captures print it. Our-row matching derives the surname from
  # this rather than taking it separately (travellers.md `#finding-our-row`), so
  # one value covers both spellings.
  player_name: Setting
  # Keys both ACBL fetch surfaces; a string because it is an identifier that may
  # carry leading zeros, never a number to do arithmetic on.
  acbl_player_number: Setting
  # The club's results calendar, which its fetch walks a month at a time.
  club_index_url: Setting


def read_configuration(source: BinaryIO) -> Configuration:
  """Parse a configuration from an open TOML stream.

  Takes a stream rather than a path so the parsing is exercisable without a
  file; `load_configuration` is the wrapper that opens the real one.

  Raises:
    ConfigurationError: the stream holds no parseable TOML, or the settings it
      states are incomplete or unusable as written.
  """
  try:
    parsed = tomllib.load(source)
  except tomllib.TOMLDecodeError as error:
    raise ConfigurationError(
      f'the configuration is not valid TOML: {error}'
    ) from error
  # TOML is UTF-8 by definition, so a file saved in any other encoding fails
  # here rather than in the parse. An accented name typed into an editor that
  # still writes Latin-1 is how that happens, and it is a fault this reports in
  # its own words like every other — not one it lets out as a traceback.
  except UnicodeDecodeError as error:
    raise ConfigurationError(
      f'the configuration is not the UTF-8 that TOML requires: {error}'
    ) from error

  try:
    return Configuration.model_validate(parsed)
  except pydantic.ValidationError as error:
    raise ConfigurationError(_what_is_wrong(error)) from error


def _what_is_wrong(error: pydantic.ValidationError) -> str:
  """What a rejected configuration has to say to whoever has to fix it.

  Named setting by setting rather than handed on as pydantic's own report, which
  spells a single missing key over three lines. A setting nobody wrote and one
  written the wrong way want different words: the first sends the reader to add
  a line, the second to look again at one they can already see — an ACBL player
  number left unquoted is a number in TOML, and telling its writer it is missing
  sends them hunting for a key that is right there.
  """
  problems = error.errors()
  absent = [
    str(problem['loc'][0])
    for problem in problems
    if problem['loc'] and problem['type'] == 'missing'
  ]
  # Carrying pydantic's own word for what is wrong with the value, since unlike
  # an absence the fault is in what was written rather than in the writing.
  unusable = [
    f'{problem["loc"][0]} ({problem["msg"].casefold()})'
    for problem in problems
    if problem['loc'] and problem['type'] != 'missing'
  ]

  complaints = []
  if absent:
    complaints.append(
      f'states no {", ".join(absent)}, and every setting is required'
    )
  if unusable:
    complaints.append(f'cannot use {"; ".join(unusable)}')
  if not complaints:
    # A rejection naming no setting at all, which nothing here can phrase better
    # than pydantic already has.
    return f'the configuration cannot be read: {error}'

  return f'the configuration {"; ".join(complaints)}'


def load_configuration(tree: PrivateTree) -> Configuration:
  """Read the configuration accompanying a private tree.

  Raises:
    ConfigurationError: no configuration file sits in the tree, or the one
      there cannot be read as a complete configuration.
  """
  path = tree.configuration_file
  # The ordinary way this fails is a tree that has never had one written, which
  # is worth more than a bare "no such file": the reader is being told to go and
  # create it, so the message says where and what goes in it.
  if not path.is_file():
    raise ConfigurationError(
      f'no configuration file at {path}; it states '
      f'{", ".join(Configuration.model_fields)}'
    )

  with path.open('rb') as source:
    return read_configuration(source)
